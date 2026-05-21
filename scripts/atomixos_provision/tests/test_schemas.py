"""Tests for atomixos_provision.schemas."""

from atomixos_provision.jobs import Job, JobState
from atomixos_provision.schemas import (
    NonceResponse,
    SubmitConfigResponse,
    ValidationResponse,
    job_event_response_from_dict,
    job_response_from_job,
    provision_result_response_from_dict,
    schema_dict,
)


def test_schema_dict_omits_none_fields():
    assert schema_dict(ValidationResponse(ok=False, error="bad")) == {
        "ok": False,
        "error": "bad",
    }


def test_simple_response_schemas():
    assert schema_dict(NonceResponse("abc")) == {"nonce": "abc"}
    assert schema_dict(SubmitConfigResponse("job", "submitted", "/api/jobs/job")) == {
        "job_id": "job",
        "state": "submitted",
        "job_url": "/api/jobs/job",
    }


def test_job_response_from_job():
    job = Job(id="job", state=JobState.FAILED, error="boom")
    job.rollback_status = "completed"

    assert schema_dict(job_response_from_job(job)) == {
        "id": "job",
        "state": "failed",
        "current_step": "submitted",
        "error": "boom",
        "rollback_status": "completed",
    }


def test_job_event_response_from_dict_keeps_public_fields():
    event = {
        "step": "service-status",
        "elapsed_seconds": 1,
        "message": "checked service",
        "service": "web.service",
        "mode": "rootful",
        "status": "running",
        "internal": object(),
    }

    assert schema_dict(job_event_response_from_dict(event)) == {
        "step": "service-status",
        "elapsed_seconds": 1.0,
        "message": "checked service",
        "service": "web.service",
        "mode": "rootful",
        "status": "running",
    }


def test_provision_result_response_preserves_current_fields():
    result = {"warnings": ["warn"], "reapply": True, "rolled_back": False}

    assert schema_dict(provision_result_response_from_dict(result)) == result


def test_job_response_uses_typed_event_and_result_schemas():
    job = Job(id="job", state=JobState.SUCCEEDED, result={"warnings": [], "reapply": False})
    job.set_stage("service-status", service="web.service", status="running")
    job.events[0]["internal"] = object()

    assert schema_dict(job_response_from_job(job)) == {
        "id": "job",
        "state": "succeeded",
        "current_step": "service-status",
        "events": [
            {
                "step": "service-status",
                "elapsed_seconds": job.events[0]["elapsed_seconds"],
                "service": "web.service",
                "status": "running",
            }
        ],
        "result": {"warnings": [], "reapply": False},
    }
