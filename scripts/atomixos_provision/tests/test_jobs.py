"""Tests for atomixos_provision.jobs module."""

import asyncio
from contextlib import suppress

import pytest

from atomixos_provision.config import ProvisionError
from atomixos_provision.jobs import Job, JobManager, JobState, StagedJobManager
from atomixos_provision.staging import (
    ensure_runtime_layout,
    publish_ready_marker,
    reserve_staged_job_slot,
    runtime_paths,
    staged_job_presence,
)


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

    @pytest.mark.asyncio
    async def test_cancelled_job_is_terminal(self):
        mgr = JobManager()
        started = asyncio.Event()

        async def work(job):
            started.set()
            raise asyncio.CancelledError()

        job = await mgr.submit(work)
        assert job is not None
        await started.wait()
        with suppress(asyncio.CancelledError):
            await mgr._task

        assert job.state == JobState.FAILED
        assert job.error == "job was cancelled"
        assert job.completed_at is not None

    @pytest.mark.asyncio
    async def test_cancelled_sync_job_is_terminal(self):
        mgr = JobManager()

        async def work(job):
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await mgr.run_sync(work)

        assert mgr.is_busy is False


class TestStagedJobManager:
    @pytest.mark.asyncio
    async def test_staged_job_times_out_waiting_for_worker_result(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
        mgr = StagedJobManager(result_timeout_seconds=0.01)
        monkeypatch.setattr(mgr, "_refresh_from_result", lambda _job: False)
        monkeypatch.setattr(mgr, "_handle_staged_timeout", lambda _job: "abandoned")

        async def work(job):
            return None

        job = await mgr.submit_staged(work)
        assert job is not None
        await mgr._task

        assert job.state == JobState.FAILED
        assert "timed out waiting for privileged apply worker" in job.error
        assert mgr.is_busy is False

    @pytest.mark.asyncio
    async def test_staged_job_keeps_slot_when_worker_has_claimed_job(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
        mgr = StagedJobManager(result_timeout_seconds=0.01, max_pending=2)
        monkeypatch.setattr(mgr, "_refresh_from_result", lambda _job: False)
        monkeypatch.setattr(mgr, "_handle_staged_timeout", lambda _job: "active")

        async def work(job):
            return None

        job = await mgr.submit_staged(work)
        task = mgr._task
        assert task is not None
        assert job is not None
        await asyncio.sleep(0.05)

        assert job.state == JobState.RUNNING
        queued = await mgr.submit_staged(work)
        queued_task = mgr._task
        assert queued is not None
        assert queued.state == JobState.RUNNING
        assert queued_task is not None

        task.cancel()
        queued_task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        with suppress(asyncio.CancelledError):
            await queued_task

        assert job.state == JobState.FAILED
        assert job.completed_at is not None


    @pytest.mark.asyncio
    async def test_staged_job_cancellation_after_queueing_keeps_monitoring(
        self, monkeypatch, tmp_path
    ):
        runtime_root = tmp_path / "run"
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
        paths = runtime_paths(runtime_root)
        cleanup_started = asyncio.Event()
        cleanup_release = asyncio.Event()
        mgr = StagedJobManager(result_timeout_seconds=60, max_pending=1)

        async def heartbeat(_job):
            try:
                await asyncio.Event().wait()
            finally:
                cleanup_started.set()
                await cleanup_release.wait()

        async def work(job):
            (paths.queue / job.id).mkdir()
            publish_ready_marker(paths, job.id)

        monkeypatch.setattr(mgr, "_heartbeat_reservation", heartbeat)
        submit_task = asyncio.create_task(mgr.submit_staged(work))
        await cleanup_started.wait()
        submit_task.cancel()
        cleanup_release.set()

        job = await submit_task

        assert job is not None
        assert job.state == JobState.RUNNING
        assert staged_job_presence(paths, job.id) == "queued"
        assert job.error is None
        assert mgr._task is not None
        mgr._task.cancel()
        with suppress(asyncio.CancelledError):
            await mgr._task


    def test_staged_timeout_keeps_queued_job_while_worker_is_active(
        self, monkeypatch, tmp_path
    ):
        runtime_root = tmp_path / "run"
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
        paths = runtime_paths(runtime_root)
        ensure_runtime_layout(paths, for_worker=True)
        (paths.active / "job-1").mkdir()
        assert reserve_staged_job_slot(paths, "job-2", 2) is True
        (paths.queue / "job-2").mkdir()
        publish_ready_marker(paths, "job-2")
        job = Job(id="job-2")
        mgr = StagedJobManager(result_timeout_seconds=0.01, max_pending=2)

        assert mgr._handle_staged_timeout(job) == "active"
        assert (paths.queue / "job-2").exists()
        assert (paths.queue / "job-2.ready").exists()

    @pytest.mark.asyncio
    async def test_staged_timeout_state_errors_fail_job(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
        mgr = StagedJobManager(result_timeout_seconds=0.01)
        monkeypatch.setattr(mgr, "_refresh_from_result", lambda _job: False)

        def timeout_state(_job):
            raise RuntimeError("permission denied")

        monkeypatch.setattr(mgr, "_handle_staged_timeout", timeout_state)

        async def work(job):
            return None

        job = await mgr.submit_staged(work)
        assert job is not None
        await mgr._task

        assert job.state == JobState.FAILED
        assert "permission denied" in job.error
        assert mgr.is_busy is False

    @pytest.mark.asyncio
    async def test_staged_runner_does_not_release_reservation_before_cancelled_work_finishes(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
        mgr = StagedJobManager(result_timeout_seconds=0.01)
        finish = asyncio.Event()
        monkeypatch.setattr(mgr, "_refresh_from_result", lambda _job: False)
        monkeypatch.setattr(mgr, "_handle_staged_timeout", lambda _job: "missing")

        async def work(job):
            await finish.wait()

        submit_task = asyncio.create_task(mgr.submit_staged(work))
        await asyncio.sleep(0)

        task = mgr._task
        assert task is None
        assert not submit_task.done()
        submit_task.cancel()
        await asyncio.sleep(0.05)
        assert not submit_task.done()
        assert mgr.is_busy is False
        finish.set()
        job = await submit_task
        assert job is not None

    @pytest.mark.asyncio
    async def test_staged_submit_cancellation_waits_for_publish_and_monitors(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
        mgr = StagedJobManager(result_timeout_seconds=0.01)
        finish = asyncio.Event()
        published = []

        def refresh(job):
            if published:
                job.state = JobState.SUCCEEDED
                return True
            return False

        monkeypatch.setattr(mgr, "_refresh_from_result", refresh)

        async def work(job):
            await finish.wait()
            published.append(job.id)

        submit_task = asyncio.create_task(mgr.submit_staged(work))
        await asyncio.sleep(0)
        submit_task.cancel()
        await asyncio.sleep(0)
        finish.set()
        job = await submit_task

        assert job is not None
        assert published == [job.id]
        assert mgr._task is not None
        await mgr._task
        assert job.state == JobState.SUCCEEDED

    @pytest.mark.asyncio
    async def test_staged_submit_returns_after_staging_before_result(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
        mgr = StagedJobManager(result_timeout_seconds=0.01)
        monkeypatch.setattr(mgr, "_refresh_from_result", lambda _job: False)
        monkeypatch.setattr(mgr, "_handle_staged_timeout", lambda _job: "missing")

        async def work(job):
            return None

        job = await mgr.submit_staged(work)
        task = mgr._task
        assert job is not None
        assert task is not None
        await asyncio.sleep(0)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

        assert job.state == JobState.FAILED
        assert job.completed_at is not None

    @pytest.mark.asyncio
    async def test_staged_submit_returns_failed_job_when_staging_fails(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
        mgr = StagedJobManager(result_timeout_seconds=0.01)

        async def work(job):
            raise RuntimeError("bad bundle")

        job = await mgr.submit_staged(work)

        assert job is not None
        assert job.state == JobState.FAILED
        assert job.error == "bad bundle"
        assert job.completed_at is not None

    @pytest.mark.asyncio
    async def test_staged_submit_does_not_retain_rejected_busy_partial_job(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
        mgr = StagedJobManager(result_timeout_seconds=0.01)

        class StagedQueueBusyError(ProvisionError):
            pass

        monkeypatch.setattr(
            "atomixos_provision.provision.StagedQueueBusyError", StagedQueueBusyError
        )

        async def work(job):
            raise StagedQueueBusyError("staged queue has pending jobs")

        rejected = await mgr.submit_staged(work)

        assert rejected is None
        assert mgr._jobs == {}

    @pytest.mark.asyncio
    async def test_staged_submit_returns_failed_job_when_reservation_fails(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
        mgr = StagedJobManager(result_timeout_seconds=0.01)

        def fail_reserve(*_args, **_kwargs):
            raise PermissionError("permission denied")

        monkeypatch.setattr("atomixos_provision.staging.reserve_staged_job_slot", fail_reserve)

        async def work(job):
            raise AssertionError("work should not run")

        job = await mgr.submit_staged(work)

        assert job is not None
        assert job.state == JobState.FAILED
        assert job.error == "permission denied"
        assert job.completed_at is not None

    @pytest.mark.asyncio
    async def test_staged_submit_refreshes_reservation_around_staging(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
        mgr = StagedJobManager(result_timeout_seconds=0.01)
        refreshes = []

        def refresh(job):
            refreshes.append(job.id)

        monkeypatch.setattr(mgr, "_refresh_reservation", refresh)
        monkeypatch.setattr(mgr, "_refresh_from_result", lambda job: True)

        async def work(job):
            refreshes.append("work")

        job = await mgr.submit_staged(work)

        assert job is not None
        assert refreshes == [job.id, "work", job.id]
        assert mgr._task is not None
        await mgr._task

    @pytest.mark.asyncio
    async def test_staged_submit_heartbeats_reservation_while_staging(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
        monkeypatch.setattr("atomixos_provision.jobs._STAGED_RESERVATION_HEARTBEAT_SECONDS", 0.01)
        mgr = StagedJobManager(result_timeout_seconds=0.01)
        finish = asyncio.Event()
        refreshes = []

        def refresh(job):
            refreshes.append(job.id)

        monkeypatch.setattr(mgr, "_refresh_reservation", refresh)
        monkeypatch.setattr(mgr, "_refresh_from_result", lambda job: True)

        async def work(job):
            await finish.wait()

        submit_task = asyncio.create_task(mgr.submit_staged(work))
        await asyncio.sleep(0.05)
        finish.set()
        job = await submit_task

        assert job is not None
        assert len(refreshes) > 2
        assert mgr._task is not None
        await mgr._task

    @pytest.mark.asyncio
    async def test_staged_get_recovers_queued_job_state(self, monkeypatch, tmp_path):
        runtime_root = tmp_path / "run"
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
        mgr = StagedJobManager(result_timeout_seconds=0.01)
        monkeypatch.setattr(mgr, "_refresh_from_result", lambda _job: False)
        monkeypatch.setattr(mgr, "_handle_staged_timeout", lambda _job: "missing")
        paths = runtime_paths(runtime_root)
        ensure_runtime_layout(paths)
        (paths.queue / "job-1").mkdir()
        (paths.queue / "job-1.ready").write_text(
            '{"job_id":"job-1","sequence":1}\n', encoding="utf-8"
        )

        job = mgr.get("job-1")

        assert job is not None
        assert job.state == JobState.SUBMITTED
        assert job.stage == "queued"
        assert mgr._task is not None
        await mgr._task
        assert job.state == JobState.FAILED

    @pytest.mark.asyncio
    async def test_staged_jobs_monitor_results_independently(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
        mgr = StagedJobManager(result_timeout_seconds=0.01)
        order = []

        def refresh(job):
            job.state = JobState.SUCCEEDED
            job.result = {"job": job.id}
            return True

        monkeypatch.setattr(mgr, "_refresh_from_result", refresh)

        async def work(job):
            order.append(job.id)

        first = await mgr.submit_staged(work)
        first_task = mgr._task
        second = await mgr.submit_staged(work)
        second_task = mgr._task
        assert first is not None
        assert second is not None
        assert first_task is not None
        assert second_task is not None
        await asyncio.gather(first_task, second_task)

        assert order == [first.id, second.id]
        assert first.state == JobState.SUCCEEDED
        assert second.state == JobState.SUCCEEDED
        assert mgr.is_busy is False

    @pytest.mark.asyncio
    async def test_staged_submit_rejects_when_pending_queue_is_full(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
        mgr = StagedJobManager(max_pending=2, result_timeout_seconds=0.01)
        finish = asyncio.Event()

        def refresh(job):
            job.state = JobState.SUCCEEDED
            return True

        monkeypatch.setattr(mgr, "_refresh_from_result", refresh)

        async def work(job):
            await finish.wait()

        first_submit = asyncio.create_task(mgr.submit_staged(work))
        await asyncio.sleep(0)
        second_submit = asyncio.create_task(mgr.submit_staged(work))
        await asyncio.sleep(0)
        third = await mgr.submit_staged(work)

        assert not first_submit.done()
        assert not second_submit.done()
        finish.set()
        first = await first_submit
        first_task = mgr._task
        second = await second_submit
        second_task = mgr._task
        assert first is not None
        assert second is not None
        assert third is None

        await asyncio.sleep(0)
        assert first_task is not None
        assert second_task is not None
        await asyncio.gather(first_task, second_task)

    @pytest.mark.asyncio
    async def test_staged_submit_starts_job_monitor(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
        mgr = StagedJobManager(result_timeout_seconds=0.01)
        ran = []

        def refresh(job):
            job.state = JobState.SUCCEEDED
            return True

        monkeypatch.setattr(mgr, "_refresh_from_result", refresh)

        async def work(job):
            ran.append(job.id)

        job = await mgr.submit_staged(work)

        assert job is not None
        await mgr._task
        assert ran == [job.id]
        assert job.state == JobState.SUCCEEDED

    @pytest.mark.asyncio
    async def test_staged_job_fails_if_worker_removes_job_without_result(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
        mgr = StagedJobManager(result_timeout_seconds=0.01)
        monkeypatch.setattr(mgr, "_refresh_from_result", lambda _job: False)
        monkeypatch.setattr(mgr, "_handle_staged_timeout", lambda _job: "missing")

        async def work(job):
            return None

        job = await mgr.submit_staged(work)
        assert job is not None
        await mgr._task

        assert job.state == JobState.FAILED
        assert "did not publish a result" in job.error
        assert mgr.is_busy is False

    @pytest.mark.asyncio
    async def test_staged_job_refreshes_result_before_timeout_failure(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
        mgr = StagedJobManager(result_timeout_seconds=0.01)
        refreshes = {"count": 0}

        def refresh(job):
            refreshes["count"] += 1
            if refreshes["count"] < 2:
                return False
            job.state = JobState.SUCCEEDED
            job.result = {"warnings": []}
            return True

        monkeypatch.setattr(mgr, "_refresh_from_result", refresh)
        monkeypatch.setattr(mgr, "_handle_staged_timeout", lambda _job: "missing")

        async def work(job):
            return None

        job = await mgr.submit_staged(work)
        assert job is not None
        await mgr._task

        assert job.state == JobState.SUCCEEDED
        assert job.result == {"warnings": []}
