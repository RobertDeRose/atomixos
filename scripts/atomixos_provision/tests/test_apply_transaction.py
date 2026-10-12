"""Tests for durable staged-apply transaction state."""

import pytest

from atomixos_provision import provision
from atomixos_provision.activation import complete_reapply, rollback_activation_marker_path
from atomixos_provision.apply_transaction import (
    ApplyReceiptPhase,
    StagedApplyTransaction,
    read_apply_receipt,
    recover_interrupted_apply,
)
from atomixos_provision.config import ProvisionError
from atomixos_provision.staging import runtime_paths


def test_transaction_records_promoted_then_committed(tmp_path):
    """Verify that transaction records promoted then committed."""
    result = {"warnings": [], "reapply": False, "forwarding_url": None}
    transaction = StagedApplyTransaction.from_manifest(
        {"job_id": "job-1", "source_sha256": "a" * 64},
        result,
    )

    transaction.mark_promoted(tmp_path)
    promoted = read_apply_receipt(tmp_path)
    assert promoted is not None
    assert promoted.phase is ApplyReceiptPhase.PROMOTED

    transaction.mark_committed(tmp_path)
    committed = read_apply_receipt(tmp_path)
    assert committed is not None
    assert committed.phase is ApplyReceiptPhase.COMMITTED
    assert committed.result == result


def test_transaction_rejects_commit_without_matching_promotion(tmp_path):
    """Verify that transaction rejects commit without matching promotion."""
    transaction = StagedApplyTransaction.from_manifest(
        {"job_id": "job-1", "source_sha256": "a" * 64},
        {"warnings": []},
    )

    with pytest.raises(ProvisionError, match="without its promoted receipt"):
        transaction.mark_committed(tmp_path)


def test_receipt_aware_recovery_keeps_committed_promotion(tmp_path):
    """Recovery keeps a committed promotion and removes its rollback root."""
    result = {"warnings": [], "reapply": True}
    transaction = StagedApplyTransaction.from_manifest(
        {"job_id": "job-1", "source_sha256": "a" * 64},
        result,
    )
    transaction.mark_promoted(tmp_path)
    transaction.mark_committed(tmp_path)
    rollback = tmp_path.parent / f"{tmp_path.name}-rollback"
    rollback.mkdir()

    recovery = recover_interrupted_apply(tmp_path)

    assert recovery.receipt is not None
    assert recovery.receipt.phase is ApplyReceiptPhase.COMMITTED
    assert not rollback.exists()


def _interrupted_reapply_roots(tmp_path):
    """Create a failed promoted config whose rollback holds an older committed config."""
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text("failed")
    StagedApplyTransaction.from_manifest(
        {"job_id": "job-1", "source_sha256": "a" * 64}, {"reapply": True}
    ).mark_promoted(config_root)
    rollback = tmp_path / "config-rollback"
    rollback.mkdir()
    (rollback / "config.toml").write_text("good")
    previous = StagedApplyTransaction.from_manifest(
        {"job_id": "job-0", "source_sha256": "b" * 64}, {"reapply": False}
    )
    previous.mark_promoted(rollback)
    previous.mark_committed(rollback)
    (tmp_path / "config.atomixos-promotion-pending").write_text("pending\n")
    return config_root


def _record_rollback_activation(monkeypatch, *, interrupt=False):
    """Record which config each rollback activation sees, optionally interrupting it."""
    activated = []

    def activate(root, _progress=None):
        """Record the active config, then interrupt or succeed."""
        activated.append((root / "config.toml").read_text())
        if interrupt:
            raise KeyboardInterrupt
        return []

    monkeypatch.setattr("atomixos_provision.activation.run_activation_sequence", activate)
    monkeypatch.setattr(provision, "reconcile_bootstrap_wan", lambda: None)
    return activated


def test_recovery_reactivates_rollback_interrupted_in_complete_reapply(tmp_path, monkeypatch):
    """A worker killed during rollback activation leaves recovery to reactivate it."""
    config_root = _interrupted_reapply_roots(tmp_path)
    activated = []

    def fail_then_interrupt(root, _progress=None):
        """Fail the candidate activation, then interrupt the rollback activation."""
        activated.append((root / "config.toml").read_text())
        if len(activated) == 1:
            return ["web.service failed"]
        raise KeyboardInterrupt

    monkeypatch.setattr(
        "atomixos_provision.activation.run_activation_sequence", fail_then_interrupt
    )
    with pytest.raises(KeyboardInterrupt):
        complete_reapply(config_root)
    assert activated == ["failed", "good"]
    assert rollback_activation_marker_path(config_root).exists()

    reactivated = _record_rollback_activation(monkeypatch)
    recovery = provision._recover_staged_apply(config_root, paths=runtime_paths(tmp_path / "run"))

    assert recovery.restored_rollback
    assert recovery.receipt is not None and recovery.receipt.job_id == "job-0"
    assert reactivated == ["good"]
    assert not rollback_activation_marker_path(config_root).exists()


def test_recovery_retries_interrupted_rollback_reactivation(tmp_path, monkeypatch):
    """Recovery keeps retrying rollback activation until one attempt finishes."""
    config_root = _interrupted_reapply_roots(tmp_path)
    paths = runtime_paths(tmp_path / "run")

    interrupted = _record_rollback_activation(monkeypatch, interrupt=True)
    with pytest.raises(KeyboardInterrupt):
        provision._recover_staged_apply(config_root, paths=paths)
    assert interrupted == ["good"]
    assert rollback_activation_marker_path(config_root).exists()

    reactivated = _record_rollback_activation(monkeypatch)
    assert provision._recover_staged_apply(config_root, paths=paths).restored_rollback
    assert reactivated == ["good"]
    assert not rollback_activation_marker_path(config_root).exists()

    assert not provision._recover_staged_apply(config_root, paths=paths).restored_rollback
    assert reactivated == ["good"]


def test_boot_recovery_clears_pending_rollback_activation(tmp_path, monkeypatch):
    """Boot recovery restores the rollback and leaves activation to ordered boot units."""
    config_root = _interrupted_reapply_roots(tmp_path)
    activated = _record_rollback_activation(monkeypatch)
    rollback_activation_marker_path(config_root).write_text("pending\n")

    recovery = provision._recover_staged_apply(config_root, boot_recovery=True)

    assert recovery.restored_rollback
    assert (config_root / "config.toml").read_text() == "good"
    assert activated == []
    assert not rollback_activation_marker_path(config_root).exists()
