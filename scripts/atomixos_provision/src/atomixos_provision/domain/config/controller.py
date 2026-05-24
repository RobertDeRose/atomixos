"""Config API routes."""

import re
from dataclasses import dataclass

from litestar import Request, post
from litestar.datastructures import ResponseHeader
from litestar.openapi.datastructures import ResponseSpec
from litestar.openapi.spec import (
    OpenAPIFormat,
    OpenAPIHeader,
    OpenAPIMediaType,
    OpenAPIType,
    Operation,
    Parameter,
    RequestBody,
    Schema,
)
from litestar.response import Response

from atomixos_provision.auth import ssh_auth_guard, ssh_auth_required_guard
from atomixos_provision.bootstrap_security import enforce_bootstrap_browser_origin
from atomixos_provision.domain.config.service import ConfigService
from atomixos_provision.exceptions import ConflictError, ValidationApiError, api_error_response
from atomixos_provision.jobs import JobManager
from atomixos_provision.schemas import (
    ApiErrorResponseBody,
    FrameworkErrorResponseBody,
    SubmitConfigResponse,
    SubmitConfigResponseBody,
    ValidationResponse,
    ValidationResponseBody,
    schema_dict,
)

__all__ = ["submit_config", "validate_config"]

_MAX_FILENAME_LEN = 255
_SAFE_FILENAME_RE = re.compile(r"^[\w\-. ]+$")
_STRING_SCHEMA = Schema(type=OpenAPIType.STRING)
_BINARY_CONFIG_BODY = RequestBody(
    required=True,
    description="Raw config.toml or compressed config bundle bytes.",
    content={
        "application/octet-stream": OpenAPIMediaType(
            schema=Schema(type=OpenAPIType.STRING, format=OpenAPIFormat.BINARY)
        )
    },
)
_CONFIG_FILENAME_HEADER = Parameter(
    name="x-config-filename",
    param_in="header",
    schema=_STRING_SCHEMA,
    description="Original filename used to detect config.toml or supported bundle formats.",
)
_OPTIONAL_SSH_AUTH_PARAMETERS = [
    Parameter(
        name="x-atomixos-nonce",
        param_in="header",
        schema=_STRING_SCHEMA,
        description="Nonce returned by /api/nonce. Required for provisioned-device re-apply.",
    ),
    Parameter(
        name="x-atomixos-signature",
        param_in="header",
        schema=_STRING_SCHEMA,
        description=(
            "SSH signature over the authenticated request payload. Required for "
            "provisioned-device re-apply."
        ),
    ),
]
_REQUIRED_SSH_AUTH_PARAMETERS = [
    Parameter(
        name="x-atomixos-nonce",
        param_in="header",
        required=True,
        schema=_STRING_SCHEMA,
        description="Nonce returned by /api/nonce.",
    ),
    Parameter(
        name="x-atomixos-signature",
        param_in="header",
        required=True,
        schema=_STRING_SCHEMA,
        description="SSH signature over the authenticated request payload.",
    ),
]
_API_ERROR_RESPONSES = {
    400: ResponseSpec(ApiErrorResponseBody, description="Invalid request or config payload"),
    401: ResponseSpec(
        FrameworkErrorResponseBody,
        description="Authentication required or browser origin rejected",
    ),
}


@dataclass
class ConfigOperation(Operation):
    """Patch Litestar-generated operations for raw binary config uploads."""

    def __post_init__(self) -> None:
        if self.operation_id == "configSubmit":
            self.request_body = _BINARY_CONFIG_BODY
            self.parameters = [
                *(self.parameters or []),
                _CONFIG_FILENAME_HEADER,
                *_OPTIONAL_SSH_AUTH_PARAMETERS,
            ]
            if self.responses and (response := self.responses.get("202")):
                response.headers = response.headers or {}
                response.headers["Location"] = OpenAPIHeader(
                    schema=Schema(type=OpenAPIType.STRING),
                    description="Job status resource URL.",
                )
        elif self.operation_id == "configValidate":
            self.request_body = _BINARY_CONFIG_BODY
            self.parameters = [
                *(self.parameters or []),
                _CONFIG_FILENAME_HEADER,
                *_REQUIRED_SSH_AUTH_PARAMETERS,
            ]


def _sanitize_filename(raw: str) -> str:
    """Sanitize user-supplied filename to a safe bounded string."""
    name = raw.strip()[:_MAX_FILENAME_LEN]
    if not name or not _SAFE_FILENAME_RE.match(name):
        return "config.toml"
    return name


@post(
    "/api/config",
    guards=[ssh_auth_guard],
    operation_id="configSubmit",
    summary="Submit a config bundle for asynchronous apply",
    status_code=202,
    operation_class=ConfigOperation,
    response_headers={
        "Location": ResponseHeader(
            name="Location",
            description="Job status resource URL.",
            documentation_only=True,
        )
    },
    responses={
        401: _API_ERROR_RESPONSES[401],
        409: ResponseSpec(
            ApiErrorResponseBody,
            description="A provision job is already running",
        ),
    },
    tags=["config"],
)
async def submit_config(
    request: Request,
    config_service: ConfigService,
    job_manager: JobManager,
) -> Response[SubmitConfigResponseBody]:
    """POST /api/config — submit config bundle, returns job ID (async)."""
    allow_reapply = bool(request.scope.get("atomixos_authenticated"))
    if not allow_reapply:
        enforce_bootstrap_browser_origin(request)
    body = await request.body()
    filename = _sanitize_filename(request.headers.get("x-config-filename", "config.toml"))

    async def provision_work(job):
        return await config_service.apply_bytes(body, filename, job, allow_reapply)

    job = await job_manager.submit(provision_work)
    if job is None:
        return api_error_response(ConflictError("a provision job is already running"))

    job_url = f"/api/jobs/{job.id}"
    return Response(
        schema_dict(
            SubmitConfigResponse(
                job_id=job.id,
                state=job.state.value,
                job_url=job_url,
            )
        ),
        headers={"Location": job_url},
        status_code=202,
    )


@post(
    "/api/validate",
    guards=[ssh_auth_required_guard],
    operation_id="configValidate",
    summary="Validate a config bundle without applying it",
    status_code=200,
    operation_class=ConfigOperation,
    responses={
        **_API_ERROR_RESPONSES,
        400: ResponseSpec(ValidationResponseBody, description="Config validation failed"),
    },
    tags=["config"],
)
async def validate_config(
    request: Request,
    config_service: ConfigService,
) -> Response[ValidationResponseBody]:
    """POST /api/validate — validate config without applying."""
    body = await request.body()
    filename = _sanitize_filename(request.headers.get("x-config-filename", "config.toml"))

    try:
        result = await config_service.validate_bytes(body, filename)
        return Response(schema_dict(ValidationResponse(ok=True, **result)))
    except Exception as exc:
        return api_error_response(ValidationApiError(str(exc)))
