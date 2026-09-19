"""Tests for provisioning dispatch policy."""

import asyncio

import pytest

from atomixos_provision.domain.config.coordinator import ProvisionCoordinator
from atomixos_provision.domain.config.service import ConfigService
from atomixos_provision.jobs import Job, JobManager, StagedJobManager


@pytest.mark.asyncio
async def test_direct_submission_applies_through_config_service(monkeypatch, tmp_path):
    service = ConfigService(tmp_path)
    manager = JobManager()
    coordinator = ProvisionCoordinator(service, manager)
    calls = []

    async def apply_bytes(body, filename, progress, allow_reapply):
        calls.append((body, filename, progress.id, allow_reapply))
        return {"warnings": []}

    monkeypatch.setattr(service, "apply_bytes", apply_bytes)
    submission = await coordinator.submit_bytes(
        b"version = 1\n", "config.toml", allow_reapply=False
    )
    assert submission.job is not None
    await asyncio.sleep(0.01)

    assert calls == [(b"version = 1\n", "config.toml", submission.job.id, False)]
    assert submission.waits_for_privileged_worker is False


@pytest.mark.asyncio
async def test_staged_submission_uses_staging_and_reports_queue_policy(monkeypatch, tmp_path):
    service = ConfigService(tmp_path)
    manager = StagedJobManager()
    coordinator = ProvisionCoordinator(service, manager)
    staged = []

    async def stage_bytes(body, filename, progress, allow_reapply):
        staged.append((body, filename, progress.id, allow_reapply))

    async def submit_staged(work):
        job = Job(id="staged-job")
        await work(job)
        return job

    monkeypatch.setattr(service, "stage_bytes", stage_bytes)
    monkeypatch.setattr(manager, "submit_staged", submit_staged)
    submission = await coordinator.submit_bytes(
        b"version = 1\n", "config.toml", allow_reapply=True
    )

    assert submission.job is not None
    assert staged == [(b"version = 1\n", "config.toml", "staged-job", True)]
    assert submission.waits_for_privileged_worker is True
    assert submission.conflict_message == "the provision queue is full"


@pytest.mark.asyncio
async def test_partial_submission_uses_exclusive_staged_admission(monkeypatch, tmp_path):
    service = ConfigService(tmp_path)
    manager = StagedJobManager()
    coordinator = ProvisionCoordinator(service, manager)
    calls = []

    async def stage_partial(operation, progress):
        calls.append((operation, progress.id))

    async def submit_staged_exclusive(work):
        job = Job(id="partial-job")
        await work(job)
        return job

    monkeypatch.setattr(service, "stage_partial", stage_partial)
    monkeypatch.setattr(manager, "submit_staged_exclusive", submit_staged_exclusive)
    submission = await coordinator.submit_partial({"op": "delete_user", "name": "admin"})

    assert calls == [({"op": "delete_user", "name": "admin"}, "partial-job")]
    assert submission.conflict_message == "the provision queue is busy"
