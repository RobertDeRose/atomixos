"""Regression coverage for worker blocking and committed-apply follow-ups."""

from pathlib import Path

import pytest

from atomixos_provision.quadlet import managed_files_are_writable, render_containers


@pytest.mark.parametrize("mode", ["ro", "rw"])
@pytest.mark.parametrize("quoted", [False, True])
def test_attached_short_volume_mount_uses_host_policy_and_warning_index(mode, quoted):
    """Attached -vVALUE forms have the same policy as separate -v VALUE arguments."""
    path = "${FILES_DIR}/quoted path" if quoted else "${FILES_DIR}/state"
    mount = f"{path}:/state:{mode}"
    attached = f'-v"{mount}"' if quoted else f"-v{mount}"
    table = {
        "app": {
            "privileged": False,
            "Container": {"Image": "alpine", "PodmanArgs": ["--pid=host", attached]},
        }
    }
    assert managed_files_are_writable(table) is (mode == "rw")
    _units, _runtime, warnings = render_containers(table, Path("/data/config"))
    assert len(warnings) == (1 if mode == "rw" else 0)
    if warnings:
        assert "PodmanArgs[1]" in warnings[0]
