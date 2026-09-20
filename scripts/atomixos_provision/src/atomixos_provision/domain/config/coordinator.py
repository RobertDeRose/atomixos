"""Provisioning submission policy shared by API and Boot UI handlers."""

from collections.abc import Callable
from dataclasses import dataclass

from atomixos_provision.domain.config.service import ConfigService
from atomixos_provision.jobs import Job, JobManager, StagedJobManager

__all__ = ["ProvisionCoordinator", "SubmissionResult"]


@dataclass(frozen=True)
class SubmissionResult:
    """Result of attempting to admit provisioning work."""

    job: Job | None
    conflict_message: str
    waits_for_privileged_worker: bool


class ProvisionCoordinator:
    """Choose direct or staged execution without leaking runner details to handlers."""

    def __init__(self, config_service: ConfigService, job_manager: JobManager) -> None:
        self._config_service = config_service
        self._job_manager = job_manager

    async def submit_bytes(
        self,
        body: bytes,
        filename: str,
        *,
        allow_reapply: bool,
        authorization: dict[str, str] | None = None,
        on_started: Callable[[str], None] | None = None,
    ) -> SubmissionResult:
        if isinstance(self._job_manager, StagedJobManager):

            async def stage_work(job: Job) -> None:
                if on_started is not None:
                    on_started(job.id)
                await self._config_service.stage_bytes(
                    body,
                    filename,
                    job,
                    allow_reapply,
                    authorization,
                )

            job = await self._job_manager.submit_staged(stage_work)
            return SubmissionResult(job, "the provision queue is full", True)

        async def apply_work(job: Job) -> dict[str, object]:
            if on_started is not None:
                on_started(job.id)
            return await self._config_service.apply_bytes(body, filename, job, allow_reapply)

        job = await self._job_manager.submit(apply_work)
        return SubmissionResult(job, "a provision job is already running", False)

    async def submit_partial(
        self,
        operation: dict[str, object],
        *,
        request_payload: bytes | None = None,
        authorization: dict[str, str] | None = None,
    ) -> SubmissionResult:
        """Submit a typed partial operation through the staged job adapter."""
        if isinstance(self._job_manager, StagedJobManager):

            async def stage_work(job: Job) -> None:
                """Stage the prepared provisioning work."""
                await self._config_service.stage_partial(
                    operation,
                    job,
                    request_payload,
                    authorization,
                )

            job = await self._job_manager.submit_staged_exclusive(stage_work)
            return SubmissionResult(job, "the provision queue is busy", True)

        async def apply_work(job: Job) -> dict[str, object]:
            return await self._config_service.apply_partial(operation, job)

        job = await self._job_manager.submit(apply_work)
        return SubmissionResult(job, "a provision job is already running", False)
