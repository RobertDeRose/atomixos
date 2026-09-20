"""Tests for durable staged-apply transaction state."""

import pytest

from atomixos_provision.apply_transaction import (
    ApplyReceiptPhase,
    StagedApplyTransaction,
    read_apply_receipt,
)
from atomixos_provision.config import ProvisionError


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
