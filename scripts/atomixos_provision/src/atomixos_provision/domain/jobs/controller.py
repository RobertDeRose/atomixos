"""Jobs API routes."""

import secrets
from dataclasses import dataclass

from litestar import Request, get
from litestar.exceptions import NotAuthorizedException
from litestar.openapi.datastructures import ResponseSpec
from litestar.openapi.spec import OpenAPIType, Operation, Parameter, Schema
from litestar.response import Response

from atomixos_provision.auth import ssh_auth_guard
from atomixos_provision.exceptions import NotFoundError, api_error_response
from atomixos_provision.jobs import JobManager
from atomixos_provision.schemas import (
    ApiErrorResponseBody,
    FrameworkErrorResponseBody,
    JobResponseBody,
    job_response_from_job,
    schema_dict,
)

__all__ = ["get_job"]

_STRING_SCHEMA = Schema(type=OpenAPIType.STRING)
_POLL_TOKEN_HEADER = Parameter(
    name="x-atomixos-poll-token",
    param_in="header",
    schema=_STRING_SCHEMA,
    description="Required for first-boot jobs created before admin SSH auth exists.",
)
_SSH_AUTH_PARAMETERS = [
    Parameter(
        name="x-atomixos-key-id",
        param_in="header",
        schema=_STRING_SCHEMA,
        description="Admin signer key identifier for provisioned jobs.",
    ),
    Parameter(
        name="x-atomixos-nonce",
        param_in="header",
        schema=_STRING_SCHEMA,
        description="Nonce returned by /api/nonce for provisioned jobs.",
    ),
    Parameter(
        name="x-atomixos-signature",
        param_in="header",
        schema=_STRING_SCHEMA,
        description="SSH signature over the authenticated request payload.",
    ),
]


@dataclass
class JobsOperation(Operation):
    """Patch Litestar-generated operations for auth/poll headers."""

    def __post_init__(self) -> None:
        if self.operation_id == "jobsGet":
            self.parameters = [
                *(self.parameters or []),
                _POLL_TOKEN_HEADER,
                *_SSH_AUTH_PARAMETERS,
            ]


@get(
    "/api/jobs/{job_id:str}",
    operation_id="jobsGet",
    summary="Get provisioning job status",
    operation_class=JobsOperation,
    responses={
        401: ResponseSpec(
            FrameworkErrorResponseBody,
            description="Poll token or SSH authentication required",
        ),
        404: ResponseSpec(ApiErrorResponseBody, description="Job not found"),
    },
    tags=["jobs"],
)
async def get_job(
    job_id: str, request: Request, job_manager: JobManager
) -> Response[JobResponseBody]:
    """GET /api/jobs/{id} — poll job status."""
    job = job_manager.get(job_id)
    if job is None:
        return api_error_response(NotFoundError("job not found"))
    supplied_token = request.headers.get("x-atomixos-poll-token", "")
    if job.poll_token:
        if not supplied_token or not secrets.compare_digest(job.poll_token, supplied_token):
            raise NotAuthorizedException(detail="valid poll token required")
    else:
        await ssh_auth_guard(request, None)  # type: ignore[arg-type]
    return Response(schema_dict(job_response_from_job(job)))
