"""Tests for atomixos_provision.jobs module."""

import asyncio
from contextlib import suppress

import pytest

from atomixos_provision.jobs import Job, JobManager, JobState


class TestJobState:
    def test_values(self):
        assert JobState.SUBMITTED.value == "submitted"
        assert JobState.RUNNING.value == "running"
        assert JobState.SUCCEEDED.value == "succeeded"
        assert JobState.FAILED.value == "failed"


class TestJob:
    def test_to_dict_minimal(self):
        job = Job(id="test-123")
        d = job.to_dict()
        assert d["id"] == "test-123"
        assert d["state"] == "submitted"
        assert d["current_step"] == "submitted"
        assert "error" not in d

    def test_to_dict_with_events(self):
        job = Job(id="test-123")
        job.set_stage("validate", "parsing config", service="web.service")
        d = job.to_dict()
        assert d["current_step"] == "validate"
        assert d["events"][0]["step"] == "validate"
        assert d["events"][0]["message"] == "parsing config"
        assert d["events"][0]["service"] == "web.service"

    def test_to_dict_with_error(self):
        job = Job(id="x", state=JobState.FAILED, error="boom")
        job.rollback_status = "completed"
        d = job.to_dict()
        assert d["error"] == "boom"
        assert d["rollback_status"] == "completed"


class TestJobManager:
    @pytest.mark.asyncio
    async def test_submit_and_complete(self):
        mgr = JobManager()

        async def work(job):
            return {"warnings": []}

        job = await mgr.submit(work)
        assert job is not None
        assert job.state == JobState.SUBMITTED

        # Wait for task to complete
        await asyncio.sleep(0.05)
        assert job.state == JobState.SUCCEEDED
        assert job.result == {"warnings": []}

    @pytest.mark.asyncio
    async def test_concurrent_rejected(self):
        mgr = JobManager()
        started = asyncio.Event()

        async def slow_work(job):
            started.set()
            await asyncio.sleep(1)
            return {}

        assert await mgr.submit(slow_work) is not None
        await started.wait()

        # Second submission should be rejected
        job2 = await mgr.submit(slow_work)
        assert job2 is None
        assert mgr.is_busy is True

        # Cleanup
        if mgr._task:
            mgr._task.cancel()
            with suppress(asyncio.CancelledError):
                await mgr._task

    @pytest.mark.asyncio
    async def test_failed_job(self):
        mgr = JobManager()

        async def failing_work(job):
            raise RuntimeError("activation failed")

        job = await mgr.submit(failing_work)
        await asyncio.sleep(0.05)
        assert job.state == JobState.FAILED
        assert "activation failed" in job.error

    @pytest.mark.asyncio
    async def test_get_job(self):
        mgr = JobManager()

        async def work(job):
            return {}

        job = await mgr.submit(work)
        await asyncio.sleep(0.05)
        retrieved = mgr.get(job.id)
        assert retrieved is job
        assert mgr.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_not_busy_after_complete(self):
        mgr = JobManager()

        async def work(job):
            return {}

        await mgr.submit(work)
        await asyncio.sleep(0.05)
        assert mgr.is_busy is False

    @pytest.mark.asyncio
    async def test_cancelled_runner_waits_for_work_before_accepting_next_job(self):
        mgr = JobManager()
        finish = asyncio.Event()

        async def work(job):
            await finish.wait()
            return {}

        job = await mgr.submit(work)
        assert job is not None
        await asyncio.sleep(0)

        assert mgr._task is not None
        mgr._task.cancel()
        await asyncio.sleep(0)

        assert mgr.is_busy is True
        assert await mgr.submit(work) is None

        finish.set()
        await mgr._task
        assert mgr.is_busy is False
