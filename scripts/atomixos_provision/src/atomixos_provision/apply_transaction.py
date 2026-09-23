"""Durable staged-apply transactions and interrupted-worker finalization."""

from __future__ import annotations

import shutil
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from atomixos_provision.activation import (
    cleanup_rollback,
    discard_initial_config,
    recover_config_root,
    rollback_root_path,
)
from atomixos_provision.config import ProvisionError
from atomixos_provision.staging import (
    RuntimePaths,
    ensure_runtime_layout,
    fsync_directory,
    queue_operation_lock,
    read_json,
    read_result,
    remove_staged_path,
    validate_job_id,
    write_json_atomic,
    write_result,
)

APPLY_RECEIPT_FILENAME = ".atomixos-apply-receipt.json"
APPLY_RECEIPT_VERSION = 2


class ApplyReceiptPhase(StrEnum):
    """Durable phase of a staged config promotion."""

    PROMOTED = "promoted"
    COMMITTED = "committed"


@dataclass(frozen=True)
class StagedApplyReceipt:
    """Durable staged-apply state used for interrupted-worker recovery."""

    job_id: str
    source_sha256: str
    result: dict[str, Any]
    phase: ApplyReceiptPhase


@dataclass(frozen=True)
class ApplyRecovery:
    """Outcome of reconciling an interrupted staged apply."""

    receipt: StagedApplyReceipt | None
    discarded_initial: bool = False


@dataclass(frozen=True)
class StagedApplyTransaction:
    """Write only the legal durable transitions for one staged apply."""

    job_id: str
    source_sha256: str
    result: dict[str, Any]

    @classmethod
    def from_manifest(
        cls,
        manifest: dict[str, Any],
        result: dict[str, Any],
    ) -> StagedApplyTransaction:
        """Create a staged apply transaction from a staged manifest."""
        job_id = validate_job_id(manifest.get("job_id", ""))
        source_sha256 = manifest.get("source_sha256")
        if not _is_sha256(source_sha256):
            raise ProvisionError("staged manifest is missing a valid source digest")
        return cls(job_id, source_sha256, result)

    def mark_promoted(self, candidate_root: Path) -> None:
        """Record that the candidate configuration has been promoted."""
        self._write_receipt(candidate_root, ApplyReceiptPhase.PROMOTED)

    def mark_committed(self, config_root: Path) -> None:
        """Record that activation of the promoted configuration committed."""
        receipt = read_apply_receipt(config_root)
        if (
            receipt is None
            or receipt.phase is not ApplyReceiptPhase.PROMOTED
            or receipt.job_id != self.job_id
            or receipt.source_sha256 != self.source_sha256
            or receipt.result != self.result
        ):
            raise ProvisionError("cannot commit staged apply without its promoted receipt")
        self._write_receipt(config_root, ApplyReceiptPhase.COMMITTED)

    def _write_receipt(self, config_root: Path, phase: ApplyReceiptPhase) -> None:
        """Persist the apply receipt at the configuration root."""
        write_json_atomic(
            config_root / APPLY_RECEIPT_FILENAME,
            {
                "version": APPLY_RECEIPT_VERSION,
                "job_id": self.job_id,
                "source_sha256": self.source_sha256,
                "result": self.result,
                "phase": phase.value,
            },
            mode=0o600,
        )


def read_apply_receipt(config_root: Path) -> StagedApplyReceipt | None:
    """Read and validate an apply transaction receipt."""
    receipt_path = config_root / APPLY_RECEIPT_FILENAME
    try:
        receipt_stat = receipt_path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(receipt_stat.st_mode) or not stat.S_ISREG(receipt_stat.st_mode):
        raise ProvisionError(f"apply receipt must be a regular file: {receipt_path}")
    if receipt_stat.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ProvisionError(f"apply receipt must be owner-only: {receipt_path}")
    receipt = read_json(receipt_path)
    if receipt.get("version") != APPLY_RECEIPT_VERSION:
        raise ProvisionError(f"unsupported apply receipt version: {receipt_path}")
    job_id = validate_job_id(receipt.get("job_id", ""))
    source_sha256 = receipt.get("source_sha256")
    if not _is_sha256(source_sha256):
        raise ProvisionError(f"apply receipt has invalid source digest: {receipt_path}")
    result = receipt.get("result")
    if not isinstance(result, dict):
        raise ProvisionError(f"apply receipt has invalid result: {receipt_path}")
    try:
        phase = ApplyReceiptPhase(receipt.get("phase"))
    except ValueError as exc:
        raise ProvisionError(f"apply receipt has invalid phase: {receipt_path}") from exc
    return StagedApplyReceipt(job_id, source_sha256, result, phase)


def committed_result_for_manifest(
    receipt: StagedApplyReceipt | None,
    job_id: str,
    manifest: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return success when the manifest matches a committed receipt."""
    if receipt is None or receipt.phase is not ApplyReceiptPhase.COMMITTED or manifest is None:
        return None
    if receipt.job_id != job_id or receipt.source_sha256 != manifest.get("source_sha256"):
        return None
    return receipt.result


def recover_interrupted_apply(config_root: Path) -> ApplyRecovery:
    """Resolve durable promotion state before publishing an interrupted result."""
    receipt = read_apply_receipt(config_root)
    if receipt is not None and receipt.phase is ApplyReceiptPhase.COMMITTED:
        cleanup_rollback(config_root)
        return ApplyRecovery(receipt)
    if (
        receipt is not None
        and receipt.phase is ApplyReceiptPhase.PROMOTED
        and not rollback_root_path(config_root).exists()
    ):
        discard_initial_config(config_root)
        return ApplyRecovery(None, discarded_initial=True)
    recover_config_root(config_root)
    return ApplyRecovery(read_apply_receipt(config_root))


def finalize_abandoned_active_jobs(
    paths: RuntimePaths,
    reason: str,
    receipt: StagedApplyReceipt | None = None,
) -> int:
    """Write terminal results for jobs left by an interrupted worker."""
    ensure_runtime_layout(paths, for_worker=True)
    finalized = 0
    with queue_operation_lock(paths):
        for active_path in sorted(paths.active.iterdir()):
            try:
                active_stat = active_path.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(active_stat.st_mode) or not stat.S_ISDIR(active_stat.st_mode):
                remove_staged_path(active_path)
                continue
            job_id = validate_job_id(active_path.name)
            if read_result(paths, job_id) is None:
                committed_receipt = _committed_receipt_for_active_job(active_path, job_id, receipt)
                if committed_receipt is not None:
                    payload = {"status": "succeeded", "result": committed_receipt.result}
                else:
                    payload = {"status": "failed", "error": reason}
                write_result(paths, job_id, payload)
            shutil.rmtree(active_path, ignore_errors=True)
            finalized += 1
        fsync_directory(paths.active)
    return finalized


def _committed_receipt_for_active_job(
    active_path: Path,
    job_id: str,
    receipt: StagedApplyReceipt | None,
) -> StagedApplyReceipt | None:
    """Return the committed receipt when it belongs to the active job."""
    if (
        receipt is None
        or receipt.phase is not ApplyReceiptPhase.COMMITTED
        or receipt.job_id != job_id
    ):
        return None
    try:
        manifest = read_json(active_path / "manifest.json")
    except (OSError, ProvisionError):
        return None
    matches = (
        manifest.get("job_id") == job_id and manifest.get("source_sha256") == receipt.source_sha256
    )
    return receipt if matches else None


def _is_sha256(value: Any) -> bool:
    """Return whether a value is a lowercase SHA-256 digest."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
