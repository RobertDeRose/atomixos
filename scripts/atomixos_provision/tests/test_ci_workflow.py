"""Regression tests for provisioning PR validation coverage."""

from pathlib import Path


def test_pr_quality_gate_has_no_branch_exclusion():
    """Dependency-update and fork PRs retain validation of their merged result."""
    root = Path(__file__).resolve().parents[3]
    workflow = (root / ".github/workflows/hk.yml").read_text()
    assert "automation/refresh-flake-lock" not in workflow
