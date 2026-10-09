"""Regression tests for provisioning PR validation coverage."""

from pathlib import Path


def _indentation(line: str) -> int:
    """Return the leading whitespace width of a YAML line."""
    return len(line) - len(line.lstrip())


def _job_block(workflow: str, job_name: str) -> list[str]:
    """Extract one job's lines up to the next sibling job."""
    lines = workflow.splitlines()
    start = next(index for index, line in enumerate(lines) if line.strip() == f"{job_name}:")
    job_indent = _indentation(lines[start])
    end = next(
        (
            index
            for index, line in enumerate(lines[start + 1 :], start + 1)
            if line.strip() and _indentation(line) <= job_indent
        ),
        len(lines),
    )
    return lines[start:end]


def _has_direct_job_condition(job_block: list[str]) -> bool:
    """Detect a direct job-level if field without matching nested step fields."""
    job_indent = _indentation(job_block[0])
    child_indents = [
        _indentation(line)
        for line in job_block[1:]
        if line.strip() and not line.lstrip().startswith("#") and _indentation(line) > job_indent
    ]
    if not child_indents:
        return False
    direct_indent = min(child_indents)
    return any(
        _indentation(line) == direct_indent and line.lstrip().startswith("if:")
        for line in job_block[1:]
    )


def test_pr_quality_gate_has_no_branch_exclusion():
    """Dependency-update and fork PRs retain validation of their merged result."""
    root = Path(__file__).resolve().parents[3]
    for name in ("hk.yml", "nix.yml"):
        workflow = (root / ".github/workflows" / name).read_text()
        assert "pull_request:" in workflow
        assert "automation/refresh-flake-lock" not in workflow


def test_quality_gate_jobs_have_no_job_level_condition():
    """Require the current CI quality and evaluation jobs to remain unconditional."""
    root = Path(__file__).resolve().parents[3]
    for workflow_name, job_name in (("hk.yml", "check"), ("nix.yml", "evaluate")):
        workflow = (root / ".github/workflows" / workflow_name).read_text()
        job_block = _job_block(workflow, job_name)
        assert not _has_direct_job_condition(job_block)


def test_job_condition_detection_uses_relative_indentation():
    """Detect nested-indented job conditions while permitting conditional steps."""
    workflow = """jobs:
    check:
      if: github.ref == 'main'
      steps:
        - name: Conditional step
          if: github.event_name == 'pull_request'
          run: echo checked
    next:
      runs-on: ubuntu-latest
"""
    assert _has_direct_job_condition(_job_block(workflow, "check"))

    nested_only = """jobs:
    check:
      steps:
        - name: Conditional step
          if: github.event_name == 'pull_request'
          run: echo checked
    next:
      runs-on: ubuntu-latest
"""
    assert not _has_direct_job_condition(_job_block(nested_only, "check"))


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
