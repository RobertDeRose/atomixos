"""Async job managers with status tracking."""

import asyncio
import threading
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from atomixos_provision.config import ProvisionError
from atomixos_provision.staging import (
    StagedTimeoutState,
    interpret_staged_result,
    staged_timeout_state,
)

__all__ = ["Job", "JobManager", "JobState", "StagedJobManager"]

# Maximum number of completed jobs to retain in memory.
_MAX_RETAINED_JOBS = 64
_DEFAULT_MAX_STAGED_JOBS = 4
_STAGED_RESERVATION_HEARTBEAT_SECONDS = 30


class JobState(StrEnum):
    """Job lifecycle states."""

    SUBMITTED = "submitted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class Job:
    """Represents a single provision job."""

    id: str
    state: JobState = JobState.SUBMITTED
    submitted_at: float = field(default_factory=time.monotonic)
    started_at: float | None = None
    completed_at: float | None = None
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    rollback_status: str | None = None  # "completed" | "failed" | "skipped"
    stage: str = "submitted"
    events: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def set_stage(
        self, name: str, detail: str | None = None, **fields: str | int | float | bool
    ) -> None:
        """Record progress for polling clients."""
        with self._lock:
            self.stage = name
            event: dict[str, Any] = {
                "step": name,
                "elapsed_seconds": round(time.monotonic() - self.submitted_at, 2),
            }
            if detail:
                event["message"] = detail
            event.update(fields)
            self.events.append(event)

    def snapshot(self) -> dict[str, Any]:
        """Return a consistent copy of mutable job state."""
        with self._lock:
            return {
                "id": self.id,
                "state": self.state,
                "submitted_at": self.submitted_at,
                "started_at": self.started_at,
                "completed_at": self.completed_at,
                "result": dict(self.result),
                "error": self.error,
                "rollback_status": self.rollback_status,
                "stage": self.stage,
                "events": [dict(event) for event in self.events],
            }

    def to_dict(self) -> dict[str, Any]:
        """Serialize job state for API response."""
        from atomixos_provision.schemas import job_response_from_job, schema_dict

        return schema_dict(job_response_from_job(self))


class JobManager:
    """Single-flight async job manager.

    Only one job runs at a time. Concurrent submissions return 409.
    Jobs are stored in memory and lost on restart.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._current_job: Job | None = None
        self._jobs: dict[str, Job] = {}
        self._task: asyncio.Task | None = None

    @property
    def is_busy(self) -> bool:
        """True if a job is currently running."""
        return self._current_job is not None and self._current_job.state in (
            JobState.SUBMITTED,
            JobState.RUNNING,
        )

    async def submit(
        self,
        work: Callable[[Job], Coroutine[Any, Any, dict[str, Any]]],
    ) -> Job | None:
        """Submit a new job. Returns the Job if accepted, None if busy (409)."""
        async with self._lock:
            if self.is_busy:
                return None

            self._evict_old_jobs()
            job = Job(id=str(uuid.uuid4()))
            self._jobs[job.id] = job
            self._current_job = job
            self._task = asyncio.create_task(self._run(job, work))
            return job

    async def run_sync(
        self,
        work: Callable[[Job], Coroutine[Any, Any, dict[str, Any]]],
    ) -> dict[str, Any] | None:
        """Run work under the same single-flight lock without retaining a job."""
        async with self._lock:
            if self.is_busy:
                return None
            job = Job(id="sync")
            self._current_job = job
        try:
            with job._lock:
                job.state = JobState.RUNNING
                job.started_at = time.monotonic()
            job.set_stage("running")
            result = await work(job)
            with job._lock:
                job.state = JobState.SUCCEEDED
            job.set_stage("completed")
            with job._lock:
                job.result = result
            return result
        except asyncio.CancelledError:
            with job._lock:
                job.state = JobState.FAILED
                job.error = "job was cancelled"
            raise
        except Exception as exc:
            with job._lock:
                job.state = JobState.FAILED
                job.error = str(exc)
                if hasattr(exc, "rollback_status"):
                    job.rollback_status = exc.rollback_status
            raise
        finally:
            with job._lock:
                job.completed_at = time.monotonic()
            async with self._lock:
                if self._current_job is job:
                    self._current_job = None

    def get(self, job_id: str) -> Job | None:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def _evict_old_jobs(self) -> None:
        """Remove oldest completed jobs when the store exceeds the cap."""
        if len(self._jobs) < _MAX_RETAINED_JOBS:
            return
        completed = [
            (jid, j)
            for jid, j in self._jobs.items()
            if j.state in (JobState.SUCCEEDED, JobState.FAILED)
        ]
        completed.sort(key=lambda x: x[1].submitted_at)
        to_remove = len(self._jobs) - _MAX_RETAINED_JOBS + 1
        for jid, _ in completed[:to_remove]:
            del self._jobs[jid]

    async def _run(
        self,
        job: Job,
        work: Callable[[Job], Coroutine[Any, Any, dict[str, Any]]],
    ) -> None:
        """Execute the job work function."""
        with job._lock:
            job.state = JobState.RUNNING
            job.started_at = time.monotonic()
        job.set_stage("running")
        try:
            work_task = asyncio.create_task(work(job))
            try:
                result = await asyncio.shield(work_task)
            except asyncio.CancelledError:
                result = await work_task
            with job._lock:
                job.state = JobState.SUCCEEDED
            job.set_stage("completed")
            with job._lock:
                job.result = result
        except asyncio.CancelledError:
            with job._lock:
                job.state = JobState.FAILED
                job.error = "job was cancelled"
            raise
        except Exception as exc:
            with job._lock:
                job.state = JobState.FAILED
                job.error = str(exc)
                # Extract rollback status if available
                if hasattr(exc, "rollback_status"):
                    job.rollback_status = exc.rollback_status
        finally:
            with job._lock:
                job.completed_at = time.monotonic()
            async with self._lock:
                if self._current_job is job:
                    self._current_job = None


class StagedJobManager(JobManager):
    """Bounded FIFO manager backed by staged result files for restart recovery."""

    def __init__(
        self,
        *,
        result_timeout_seconds: float | None = None,
        max_pending: int = _DEFAULT_MAX_STAGED_JOBS,
    ) -> None:
        super().__init__()
        if result_timeout_seconds is None:
            from atomixos_provision.provision import STAGED_RESULT_TIMEOUT_SECONDS

            result_timeout_seconds = STAGED_RESULT_TIMEOUT_SECONDS
        self._result_timeout_seconds = result_timeout_seconds
        self._max_pending = max_pending
        self._recovery_lock = threading.Lock()
        self._monitored_job_ids: set[str] = set()

    @property
    def is_busy(self) -> bool:
        """True if any staged job is currently being prepared or monitored."""
        return any(
            job.state in (JobState.SUBMITTED, JobState.RUNNING) for job in self._jobs.values()
        )

    async def submit_staged(
        self,
        work: Callable[[Job], Coroutine[Any, Any, None]],
    ) -> Job | None:
        return await self._submit_staged(work, exclusive=False)

    async def submit_staged_exclusive(
        self,
        work: Callable[[Job], Coroutine[Any, Any, None]],
    ) -> Job | None:
        """Submit a staged job while holding admission closed until staging completes."""
        return await self._submit_staged(work, exclusive=True)

    async def _submit_staged(
        self,
        work: Callable[[Job], Coroutine[Any, Any, None]],
        *,
        exclusive: bool,
    ) -> Job | None:
        job = Job(id=str(uuid.uuid4()))
        async with self._lock:
            self._evict_old_jobs()
            from atomixos_provision.provision import _runtime_paths
            from atomixos_provision.staging import reserve_staged_job_slot

            try:
                if not reserve_staged_job_slot(_runtime_paths(), job.id, self._max_pending):
                    return None
            except Exception as exc:
                with job._lock:
                    job.state = JobState.FAILED
                    job.error = str(exc)
                    job.completed_at = time.monotonic()
                self._jobs[job.id] = job
                return job
            self._jobs[job.id] = job
            if exclusive:
                return await self._stage_with_busy_translation(job, work, lock_held=True)
        return await self._stage_with_busy_translation(job, work, lock_held=False)

    async def _stage_with_busy_translation(
        self,
        job: Job,
        work: Callable[[Job], Coroutine[Any, Any, None]],
        *,
        lock_held: bool,
    ) -> Job | None:
        try:
            return await self._stage_and_monitor(job, work)
        except Exception as exc:
            from atomixos_provision.provision import StagedQueueBusyError

            if isinstance(exc, StagedQueueBusyError):
                if lock_held:
                    self._jobs.pop(job.id, None)
                else:
                    async with self._lock:
                        self._jobs.pop(job.id, None)
                return None
            return job

    def get(self, job_id: str) -> Job | None:
        """Return the staged job for the requested identifier."""
        from atomixos_provision.staging import validate_job_id

        try:
            validate_job_id(job_id)
        except ProvisionError:
            return None
        with self._recovery_lock:
            job = super().get(job_id)
            if job is not None:
                self._refresh_from_result(job)
                return job
            recovered = self._job_from_result(job_id)
            if recovered is not None:
                self._jobs[job_id] = recovered
            return recovered

    async def _stage_and_monitor(
        self,
        job: Job,
        work: Callable[[Job], Coroutine[Any, Any, None]],
    ) -> Job:
        with job._lock:
            job.state = JobState.RUNNING
            job.started_at = time.monotonic()
        job.set_stage("running")
        heartbeat_task: asyncio.Task | None = None
        work_task: asyncio.Task | None = None
        staged = False
        try:
            self._refresh_reservation(job)
            heartbeat_task = asyncio.create_task(self._heartbeat_reservation(job))
            work_task = asyncio.create_task(work(job))
            try:
                await asyncio.shield(work_task)
            except asyncio.CancelledError:
                await work_task
            staged = True
            heartbeat_task.cancel()
            maintenance_errors: list[BaseException] = []
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                maintenance_errors.append(exc)
            heartbeat_task = None
            try:
                self._refresh_reservation(job)
            except Exception as exc:
                maintenance_errors.append(exc)
            self._mark_queued(job, maintenance_errors)
        except asyncio.CancelledError:
            if staged:
                maintenance_errors = []
                if heartbeat_task is not None:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
                    except Exception as exc:
                        maintenance_errors.append(exc)
                    heartbeat_task = None
                try:
                    self._refresh_reservation(job)
                except Exception as exc:
                    maintenance_errors.append(exc)
                self._mark_queued(job, maintenance_errors)
                self._start_monitor_if_possible(job)
                return job
            try:
                self._release_reservation(job)
            except Exception as exc:
                self._mark_failed(job, exc)
                raise
            self._mark_failed(job, "staged job manager task was cancelled")
            raise
        except Exception as original_error:
            if staged:
                self._mark_queued(job, [original_error])
                self._start_monitor_if_possible(job)
                return job
            failure: BaseException = original_error
            try:
                self._release_reservation(job)
            except Exception as cleanup_error:
                failure = cleanup_error
            from atomixos_provision.provision import StagedQueueBusyError

            self._mark_failed(job, failure)
            if isinstance(failure, StagedQueueBusyError):
                raise
            return job
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    self._mark_failed(job, exc)
        self._start_monitor_if_possible(job)
        return job

    @staticmethod
    def _mark_queued(job: Job, maintenance_errors: list[BaseException]) -> None:
        """Publish queued state for a staged job."""
        detail = "waiting for privileged apply worker"
        if maintenance_errors:
            detail += "; post-publication reservation maintenance failed: " + "; ".join(
                str(error) for error in maintenance_errors
            )
        job.set_stage("queued", detail)

    @staticmethod
    def _mark_failed(job: Job, error: BaseException | str) -> None:
        """Publish terminal failure for a staged job."""
        with job._lock:
            job.state = JobState.FAILED
            job.error = str(error)
            if hasattr(error, "rollback_status"):
                job.rollback_status = error.rollback_status
            job.completed_at = time.monotonic()

    async def _heartbeat_reservation(self, job: Job) -> None:
        while True:
            await asyncio.sleep(_STAGED_RESERVATION_HEARTBEAT_SECONDS)
            self._refresh_reservation(job)

    async def _monitor_staged(self, job: Job) -> None:
        try:
            deadline = time.monotonic() + self._result_timeout_seconds
            while job.state in (JobState.SUBMITTED, JobState.RUNNING):
                if self._refresh_from_result(job):
                    break
                if time.monotonic() >= deadline:
                    timeout_state = self._handle_staged_timeout(job)
                    if self._refresh_from_result(job):
                        break
                    if timeout_state in {
                        StagedTimeoutState.WAITING,
                        StagedTimeoutState.CLAIMED,
                    }:
                        deadline = time.monotonic() + self._result_timeout_seconds
                        if timeout_state is StagedTimeoutState.CLAIMED:
                            job.set_stage("running", "privileged apply worker is running")
                        else:
                            job.set_stage("queued", "waiting for privileged apply worker")
                        continue
                    if timeout_state is StagedTimeoutState.MISSING:
                        raise ProvisionError("privileged apply worker did not publish a result")
                    raise ProvisionError("timed out waiting for privileged apply worker")
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            with job._lock:
                job.state = JobState.FAILED
                job.error = "staged job manager task was cancelled"
                job.completed_at = time.monotonic()
            raise
        except Exception as exc:
            with job._lock:
                job.state = JobState.FAILED
                job.error = str(exc)
                if hasattr(exc, "rollback_status"):
                    job.rollback_status = exc.rollback_status
                job.completed_at = time.monotonic()
        finally:
            self._monitored_job_ids.discard(job.id)

    def _refresh_from_result(self, job: Job) -> bool:
        try:
            from atomixos_provision.provision import _runtime_paths
            from atomixos_provision.staging import read_result

            result = read_result(_runtime_paths(), job.id)
        except FileNotFoundError:
            return False
        if result is None:
            return False
        with job._lock:
            outcome = interpret_staged_result(result)
            job.completed_at = job.completed_at or time.monotonic()
            if outcome.succeeded:
                job.state = JobState.SUCCEEDED
                job.result = outcome.payload
                job.error = None
                job.stage = "completed"
            else:
                job.state = JobState.FAILED
                job.error = outcome.error
                job.rollback_status = outcome.rollback_status
                job.stage = "failed"
        return True

    def _release_reservation(self, job: Job) -> None:
        try:
            from atomixos_provision.provision import _runtime_paths
            from atomixos_provision.staging import release_staged_job_slot

            release_staged_job_slot(_runtime_paths(), job.id)
        except FileNotFoundError:
            return

    def _refresh_reservation(self, job: Job) -> None:
        try:
            from atomixos_provision.provision import _runtime_paths
            from atomixos_provision.staging import refresh_staged_job_slot

            refresh_staged_job_slot(_runtime_paths(), job.id)
        except FileNotFoundError:
            return

    def _job_from_result(self, job_id: str) -> Job | None:
        job = Job(id=job_id)
        if self._refresh_from_result(job):
            return job
        try:
            from atomixos_provision.provision import _runtime_paths
            from atomixos_provision.staging import staged_job_presence

            presence = staged_job_presence(_runtime_paths(), job_id)
        except FileNotFoundError:
            return None
        if presence == "queued":
            job.set_stage("queued", "waiting for privileged apply worker")
            self._start_monitor_if_possible(job)
            return job
        if presence == "active":
            with job._lock:
                job.state = JobState.RUNNING
                job.started_at = time.monotonic()
            job.set_stage("running", "privileged apply worker is running")
            self._start_monitor_if_possible(job)
            return job
        return None

    def _start_monitor_if_possible(self, job: Job) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        if job.id in self._monitored_job_ids:
            return
        self._monitored_job_ids.add(job.id)
        self._task = asyncio.create_task(self._monitor_staged(job))

    def _handle_staged_timeout(self, job: Job) -> StagedTimeoutState:
        """Reconcile a staged job after result monitoring times out."""
        try:
            from atomixos_provision.provision import _runtime_paths

            return staged_timeout_state(_runtime_paths(), job.id)
        except ProvisionError:
            raise
        except Exception as exc:
            raise ProvisionError("cannot determine staged job timeout state") from exc
