"""Tests for the provisioning package's runtime dependency contract."""

import tomllib
from pathlib import Path

PROJECT_FILE = Path(__file__).parents[1] / "pyproject.toml"


def test_runtime_uses_base_uvicorn_without_standard_extras():
    """Verify that runtime uses base uvicorn without standard extras."""
    project = tomllib.loads(PROJECT_FILE.read_text())
    dependencies = project["project"]["dependencies"]

    assert any(dependency.startswith("uvicorn>=") for dependency in dependencies)
    assert not any(dependency.startswith("uvicorn[") for dependency in dependencies)
    assert not any("uvloop" in dependency for dependency in dependencies)
