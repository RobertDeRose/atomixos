"""Regression tests for provisioning PR validation coverage."""

from pathlib import Path


def _job_block(workflow: str, job_name: str) -> list[str]:
    lines = workflow.splitlines()
    start = lines.index(f"  {job_name}:")
    end = next(
        (
            index
            for index, line in enumerate(lines[start + 1 :], start + 1)
            if line.startswith("  ") and not line.startswith("    ")
        ),
        len(lines),
    )
    return lines[start:end]


def test_pr_quality_gate_has_no_branch_exclusion():
    """Dependency-update and fork PRs retain validation of their merged result."""
    root = Path(__file__).resolve().parents[3]
    for name in ("hk.yml", "nix.yml"):
        workflow = (root / ".github/workflows" / name).read_text()
        assert "pull_request:" in workflow
        assert "automation/refresh-flake-lock" not in workflow


def test_quality_gate_jobs_have_no_job_level_condition():
    root = Path(__file__).resolve().parents[3]
    for workflow_name, job_name in (("hk.yml", "check"), ("nix.yml", "evaluate")):
        workflow = (root / ".github/workflows" / workflow_name).read_text()
        job_block = _job_block(workflow, job_name)
        assert not any(line.startswith("    if:") for line in job_block)


def test_hk_quality_gate_is_separate_from_nix_evaluation():
    root = Path(__file__).resolve().parents[3]
    workflow = (root / ".github/workflows/hk.yml").read_text()
    assert "jdx/mise-action@" in workflow
    assert "install: false" in workflow
    assert "run: mise x -- hk check -a\n" in workflow
    assert "mise install" not in workflow
    assert "install-nix-action" not in workflow
    assert "flake check" not in workflow
    assert 'steps = linters' in (root / "hk.pkl").read_text()
    assert "flake check" not in (root / "hk.pkl").read_text()


def test_nix_evaluation_preserves_platform_coverage_without_builds():
    root = Path(__file__).resolve().parents[3]
    workflow = (root / ".github/workflows/nix.yml").read_text()
    assert "system: aarch64-linux" in workflow
    assert "system: aarch64-darwin" in workflow
    assert "install-nix-action@" in workflow
    assert 'flake check --no-build --system "${{ matrix.system }}"' in workflow
    assert "mise-action" not in workflow
    assert "hk check" not in workflow
