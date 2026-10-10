"""Regression tests for reviewed recovery, monitoring, and deployment contracts."""

from pathlib import Path

import pytest

from atomixos_provision.quadlet import managed_files_are_writable, render_containers

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "args",
    [
        ['--volume "${FILES_DIR}/quoted path:/state:rw"'],
        ['--mount "type=bind,source=${FILES_DIR}/quoted path,target=/state,rw"'],
        ["--pid=host --volume=${FILES_DIR}/state:/state:rw"],
        ["--volume", '"${FILES_DIR}/quoted path:/state:rw"'],
    ],
)
def test_combined_quoted_podman_mounts_preserve_warning_indices(args):
    """All supported argument groupings participate in host permission analysis."""
    table = {"app": {"privileged": False, "Container": {"Image": "alpine", "PodmanArgs": args}}}
    assert managed_files_are_writable(table)
    _units, _runtime, warnings = render_containers(table, Path("/data/config"))
    assert len(warnings) == 1
    assert f"PodmanArgs[{len(args) - 1}]" in warnings[0]
