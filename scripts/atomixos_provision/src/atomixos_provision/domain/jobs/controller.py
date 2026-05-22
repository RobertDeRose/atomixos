"""Jobs API routes."""

from litestar import get
from litestar.openapi.datastructures import ResponseSpec
from litestar.response import Response

from atomixos_provision.exceptions import NotFoundError, api_error_response
from atomixos_provision.jobs import JobManager
from atomixos_provision.schemas import (
    ApiErrorResponseBody,
    JobResponseBody,
    job_response_from_job,
    schema_dict,
)

__all__ = ["get_job"]


@get(
    "/api/jobs/{job_id:str}",
    operation_id="jobsGet",
    summary="Get provisioning job status",
    responses={
        404: ResponseSpec(ApiErrorResponseBody, description="Job not found"),
    },
    tags=["jobs"],
)
async def get_job(job_id: str, job_manager: JobManager) -> Response[JobResponseBody]:
    """GET /api/jobs/{id} — poll job status."""
    job = job_manager.get(job_id)
    if job is None:
        return api_error_response(NotFoundError("job not found"))
    return Response(schema_dict(job_response_from_job(job)))
