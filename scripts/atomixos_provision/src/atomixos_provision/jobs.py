"""Async job manager with single-flight execution and status tracking."""

import asyncio
import threading
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = ["Job", "JobManager", "JobState"]

# Maximum number of completed jobs to retain in memory.
_MAX_RETAINED_JOBS = 64


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
