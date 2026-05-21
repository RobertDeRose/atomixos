"""Typed API response schemas."""

from dataclasses import asdict, dataclass, field
from typing import Any, NotRequired, TypedDict

from atomixos_provision.jobs import Job, JobState

__all__ = [
    "ApiErrorResponseBody",
    "FrameworkErrorResponseBody",
    "JobEventResponse",
    "JobResponse",
    "JobResponseBody",
    "NonceResponse",
    "NonceResponseBody",
    "ProvisionResultResponse",
    "SubmitConfigResponse",
    "SubmitConfigResponseBody",
    "ValidationResponse",
    "ValidationResponseBody",
    "job_response_from_job",
    "schema_dict",
]


def schema_dict(value: Any) -> dict[str, Any]:
    """Convert a dataclass schema to a dict without fields set to None."""
    return {key: item for key, item in asdict(value).items() if item is not None}


@dataclass(frozen=True)
class NonceResponse:
    nonce: str


class NonceResponseBody(TypedDict):
    nonce: str


class ApiErrorResponseBody(TypedDict):
    error: str


class FrameworkErrorResponseBody(TypedDict):
    status_code: int
    detail: str


@dataclass(frozen=True)
class SubmitConfigResponse:
    job_id: str
    state: str
    job_url: str
    poll_token: str | None = None


class SubmitConfigResponseBody(TypedDict):
    job_id: str
    state: str
    job_url: str
    poll_token: NotRequired[str]


@dataclass(frozen=True)
class ValidationResponse:
    ok: bool
    error: str | None = None
    warnings: list[str] | None = None


class ValidationResponseBody(TypedDict):
    ok: bool
    error: NotRequired[str]
    warnings: NotRequired[list[str]]


@dataclass(frozen=True)
class ProvisionResultResponse:
    warnings: list[str] = field(default_factory=list)
    reapply: bool | None = None
    rolled_back: bool | None = None
    forwarding_url: str | None = None


def provision_result_response_from_dict(result: dict[str, Any]) -> ProvisionResultResponse:
    """Build a typed provision result while preserving current result fields."""
    return ProvisionResultResponse(
        warnings=list(result.get("warnings", [])),
        reapply=result.get("reapply"),
        rolled_back=result.get("rolled_back"),
        forwarding_url=result.get("forwarding_url"),
    )


@dataclass(frozen=True)
class JobEventResponse:
    step: str
    elapsed_seconds: float
    message: str | None = None
    service: str | None = None
    mode: str | None = None
    status: str | None = None


def job_event_response_from_dict(event: dict[str, Any]) -> JobEventResponse:
    """Build a typed job event from internal progress data."""
    return JobEventResponse(
        step=str(event["step"]),
        elapsed_seconds=float(event["elapsed_seconds"]),
        message=event.get("message"),
        service=event.get("service"),
        mode=event.get("mode"),
        status=event.get("status"),
    )


@dataclass(frozen=True)
class JobResponse:
    id: str
    state: str
    current_step: str
    events: list[dict[str, Any]] | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    rollback_status: str | None = None
    duration_seconds: float | None = None


class JobResponseBody(TypedDict):
    id: str
    state: str
    current_step: str
    events: NotRequired[list[dict[str, Any]]]
    error: NotRequired[str]
    result: NotRequired[dict[str, Any]]
    rollback_status: NotRequired[str]
    duration_seconds: NotRequired[float]


def job_response_from_job(job: Job) -> JobResponse:
    """Build a typed response schema from a job."""
    snapshot = job.snapshot()
    duration_seconds = None
    if snapshot["completed_at"] and snapshot["started_at"]:
        duration_seconds = round(snapshot["completed_at"] - snapshot["started_at"], 2)
    result = None
    if snapshot["result"]:
        result = schema_dict(provision_result_response_from_dict(snapshot["result"]))
    state = snapshot["state"]
    events = [schema_dict(job_event_response_from_dict(event)) for event in snapshot["events"]]
    return JobResponse(
        id=snapshot["id"],
        state=state.value if isinstance(state, JobState) else str(state),
        current_step=snapshot["stage"],
        events=events or None,
        error=snapshot["error"],
        result=result,
        rollback_status=snapshot["rollback_status"],
        duration_seconds=duration_seconds,
    )
