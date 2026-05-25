"""Config API routes."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from litestar import Request, delete, get, patch, post, put
from litestar.datastructures import ResponseHeader
from litestar.openapi.datastructures import ResponseSpec
from litestar.openapi.spec import (
    OpenAPIFormat,
    OpenAPIHeader,
    OpenAPIMediaType,
    OpenAPIType,
    Operation,
    Parameter,
    Reference,
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

__all__ = [
    "delete_container",
    "delete_container_network",
    "delete_container_volume",
    "delete_partial_user",
    "export_config",
    "patch_partial_network",
    "put_container",
    "put_container_network",
    "put_container_volume",
    "put_partial_user",
    "submit_config",
    "validate_config",
]

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


def _object_schema(
    properties: dict[str, Schema], required: list[str] | None = None
) -> Schema:
    return Schema(
        type=OpenAPIType.OBJECT,
        properties=properties,
        required=required,
        additional_properties=False,
    )


def _json_body(schema: Schema | Reference, description: str) -> RequestBody:
    return RequestBody(
        required=True,
        description=description,
        content={
            "application/json": OpenAPIMediaType(schema=schema)
        },
    )


_BOOL_SCHEMA = Schema(type=OpenAPIType.BOOLEAN)
_ARRAY_SCHEMA = Schema(type=OpenAPIType.ARRAY, items=_STRING_SCHEMA)
_OBJECT_MAP_SCHEMA = Schema(type=OpenAPIType.OBJECT, additional_properties=True)
_NULLABLE_STRING_SCHEMA = Schema(type=[OpenAPIType.STRING, OpenAPIType.NULL])
_USER_BODY = _json_body(
    _object_schema(
        {
            "isAdmin": _BOOL_SCHEMA,
            "ssh_key": _STRING_SCHEMA,
            "shell": _STRING_SCHEMA,
        },
        ["isAdmin", "ssh_key"],
    ),
    "User declaration to merge into config.toml.",
)
_NETWORK_BODY = _json_body(
    _object_schema(
        {
            "dns_servers": _ARRAY_SCHEMA,
            "dns_search_domains": _ARRAY_SCHEMA,
            "default_gateway": _NULLABLE_STRING_SCHEMA,
            "interfaces": _OBJECT_MAP_SCHEMA,
            "dnsmasq": _OBJECT_MAP_SCHEMA,
            "ntp": _OBJECT_MAP_SCHEMA,
            "firewall": _OBJECT_MAP_SCHEMA,
        }
    ),
    "Network fields to merge into config.toml.",
)
_CONTAINER_BODY = _json_body(
    _object_schema(
        {
            "privileged": _BOOL_SCHEMA,
            "Unit": _OBJECT_MAP_SCHEMA,
            "Container": _OBJECT_MAP_SCHEMA,
            "Install": _OBJECT_MAP_SCHEMA,
        },
        ["privileged", "Container"],
    ),
    "Quadlet container declaration to merge into config.toml.",
)
_CONTAINER_NETWORK_BODY = _json_body(
    _object_schema({"Network": _OBJECT_MAP_SCHEMA}, ["Network"]),
    "Quadlet network declaration to merge into config.toml.",
)
_CONTAINER_VOLUME_BODY = _json_body(
    _object_schema({"Volume": _OBJECT_MAP_SCHEMA}, ["Volume"]),
    "Quadlet volume declaration to merge into config.toml.",
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
_PARTIAL_RESPONSES = {
    **_API_ERROR_RESPONSES,
    409: ResponseSpec(ApiErrorResponseBody, description="A provision job is already running"),
}
_REQUIRED_AUTH_OPERATION_IDS = {
    "configExport",
    "configUsersPut",
    "configUsersDelete",
    "configNetworkPatch",
    "configContainersPut",
    "configContainersDelete",
    "configContainerNetworksPut",
    "configContainerNetworksDelete",
    "configContainerVolumesPut",
    "configContainerVolumesDelete",
    "configValidate",
}
_PARTIAL_REQUEST_BODIES = {
    "configUsersPut": _USER_BODY,
    "configNetworkPatch": _NETWORK_BODY,
    "configContainersPut": _CONTAINER_BODY,
    "configContainerNetworksPut": _CONTAINER_NETWORK_BODY,
    "configContainerVolumesPut": _CONTAINER_VOLUME_BODY,
}


@dataclass
class ConfigOperation(Operation):
    """Patch generated config operations for binary uploads and auth docs."""

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
        elif self.operation_id in _REQUIRED_AUTH_OPERATION_IDS:
            if self.operation_id in _PARTIAL_REQUEST_BODIES:
                self.request_body = _PARTIAL_REQUEST_BODIES[self.operation_id]
            if self.operation_id == "configExport" and self.responses:
                self.responses["200"].content = {
                    "application/toml": OpenAPIMediaType(schema=Schema(type=OpenAPIType.STRING))
                }
            if self.operation_id == "configValidate":
                self.request_body = _BINARY_CONFIG_BODY
            self.parameters = [
                *(self.parameters or []),
                *_REQUIRED_SSH_AUTH_PARAMETERS,
            ]
            if self.operation_id == "configValidate":
                self.parameters.insert(len(self.parameters) - 2, _CONFIG_FILENAME_HEADER)
            if self.responses and (response := self.responses.get("202")):
                response.headers = response.headers or {}
                response.headers["Location"] = OpenAPIHeader(
                    schema=Schema(type=OpenAPIType.STRING),
                    description="Job status resource URL.",
                )


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


@get(
    "/api/config/export",
    guards=[ssh_auth_required_guard],
    operation_id="configExport",
    summary="Export the current canonical config.toml",
    operation_class=ConfigOperation,
    responses={**_API_ERROR_RESPONSES},
    tags=["config"],
)
async def export_config(config_service: ConfigService) -> Response[bytes]:
    return Response(
        config_service.export_config(),
        media_type="application/toml",
        headers={"content-disposition": 'attachment; filename="config.toml"'},
    )


@put(
    "/api/config/users/{name:str}",
    guards=[ssh_auth_required_guard],
    operation_id="configUsersPut",
    summary="Create or replace a user and asynchronously apply config",
    status_code=202,
    operation_class=ConfigOperation,
    responses=_PARTIAL_RESPONSES,
    tags=["config"],
)
async def put_partial_user(
    name: str,
    data: dict[str, Any],
    config_service: ConfigService,
    job_manager: JobManager,
) -> Response[SubmitConfigResponseBody]:
    return await _submit_partial_job(
        job_manager, lambda job: config_service.put_user(name, dict(data), job)
    )


@delete(
    "/api/config/users/{name:str}",
    guards=[ssh_auth_required_guard],
    operation_id="configUsersDelete",
    summary="Delete a user and asynchronously apply config",
    status_code=202,
    operation_class=ConfigOperation,
    responses=_PARTIAL_RESPONSES,
    tags=["config"],
)
async def delete_partial_user(
    name: str,
    config_service: ConfigService,
    job_manager: JobManager,
) -> Response[SubmitConfigResponseBody]:
    return await _submit_partial_job(
        job_manager, lambda job: config_service.delete_user(name, job)
    )


@patch(
    "/api/config/network",
    guards=[ssh_auth_required_guard],
    operation_id="configNetworkPatch",
    summary="Patch network config and asynchronously apply config",
    status_code=202,
    operation_class=ConfigOperation,
    responses=_PARTIAL_RESPONSES,
    tags=["config"],
)
async def patch_partial_network(
    data: dict[str, Any],
    config_service: ConfigService,
    job_manager: JobManager,
) -> Response[SubmitConfigResponseBody]:
    return await _submit_partial_job(
        job_manager, lambda job: config_service.patch_network(dict(data), job)
    )


@put(
    "/api/config/containers/{name:str}",
    guards=[ssh_auth_required_guard],
    operation_id="configContainersPut",
    summary="Create or replace a container and asynchronously apply config",
    status_code=202,
    operation_class=ConfigOperation,
    responses=_PARTIAL_RESPONSES,
    tags=["config"],
)
async def put_container(
    name: str,
    data: dict[str, Any],
    config_service: ConfigService,
    job_manager: JobManager,
) -> Response[SubmitConfigResponseBody]:
    return await _submit_partial_job(
        job_manager, lambda job: config_service.put_resource("container", name, dict(data), job)
    )


@delete(
    "/api/config/containers/{name:str}",
    guards=[ssh_auth_required_guard],
    operation_id="configContainersDelete",
    summary="Delete a container and asynchronously apply config",
    status_code=202,
    operation_class=ConfigOperation,
    responses=_PARTIAL_RESPONSES,
    tags=["config"],
)
async def delete_container(
    name: str, config_service: ConfigService, job_manager: JobManager
) -> Response[SubmitConfigResponseBody]:
    return await _submit_partial_job(
        job_manager, lambda job: config_service.delete_resource("container", name, job)
    )


@put(
    "/api/config/container-networks/{name:str}",
    guards=[ssh_auth_required_guard],
    operation_id="configContainerNetworksPut",
    summary="Create or replace a container network and asynchronously apply config",
    status_code=202,
    operation_class=ConfigOperation,
    responses=_PARTIAL_RESPONSES,
    tags=["config"],
)
async def put_container_network(
    name: str,
    data: dict[str, Any],
    config_service: ConfigService,
    job_manager: JobManager,
) -> Response[SubmitConfigResponseBody]:
    return await _submit_partial_job(
        job_manager, lambda job: config_service.put_resource("network", name, dict(data), job)
    )


@delete(
    "/api/config/container-networks/{name:str}",
    guards=[ssh_auth_required_guard],
    operation_id="configContainerNetworksDelete",
    summary="Delete a container network and asynchronously apply config",
    status_code=202,
    operation_class=ConfigOperation,
    responses=_PARTIAL_RESPONSES,
    tags=["config"],
)
async def delete_container_network(
    name: str, config_service: ConfigService, job_manager: JobManager
) -> Response[SubmitConfigResponseBody]:
    return await _submit_partial_job(
        job_manager, lambda job: config_service.delete_resource("network", name, job)
    )


@put(
    "/api/config/container-volumes/{name:str}",
    guards=[ssh_auth_required_guard],
    operation_id="configContainerVolumesPut",
    summary="Create or replace a container volume and asynchronously apply config",
    status_code=202,
    operation_class=ConfigOperation,
    responses=_PARTIAL_RESPONSES,
    tags=["config"],
)
async def put_container_volume(
    name: str,
    data: dict[str, Any],
    config_service: ConfigService,
    job_manager: JobManager,
) -> Response[SubmitConfigResponseBody]:
    return await _submit_partial_job(
        job_manager, lambda job: config_service.put_resource("volume", name, dict(data), job)
    )


@delete(
    "/api/config/container-volumes/{name:str}",
    guards=[ssh_auth_required_guard],
    operation_id="configContainerVolumesDelete",
    summary="Delete a container volume and asynchronously apply config",
    status_code=202,
    operation_class=ConfigOperation,
    responses=_PARTIAL_RESPONSES,
    tags=["config"],
)
async def delete_container_volume(
    name: str, config_service: ConfigService, job_manager: JobManager
) -> Response[SubmitConfigResponseBody]:
    return await _submit_partial_job(
        job_manager, lambda job: config_service.delete_resource("volume", name, job)
    )


async def _submit_partial_job(
    job_manager: JobManager, work: Callable[[Any], Any]
) -> Response[SubmitConfigResponseBody]:
    job = await job_manager.submit(work)
    if job is None:
        return api_error_response(ConflictError("a provision job is already running"))
    job_url = f"/api/jobs/{job.id}"
    return Response(
        schema_dict(SubmitConfigResponse(job_id=job.id, state=job.state.value, job_url=job_url)),
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
