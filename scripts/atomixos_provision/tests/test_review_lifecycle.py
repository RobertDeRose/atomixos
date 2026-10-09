"""Regression tests for reviewed recovery, monitoring, and deployment contracts."""

import subprocess
from pathlib import Path

import pytest

from atomixos_provision.activation import promotion_marker_path
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


@pytest.mark.parametrize(
    ("entry", "symlink", "pending", "open_wan"),
    [
        (".first-config", False, False, False),
        ("config.toml", False, False, False),
        ("admin-signers", False, False, True),
        (".first-config", True, False, True),
        ("config.toml", True, False, True),
        (".first-config", False, True, True),
    ],
)
def test_wan_firewall_uses_non_symlink_marker_or_config(
    tmp_path, entry, symlink, pending, open_wan
):
    """Execute the production toggle with a fake nft command and temporary config."""
    root = tmp_path / "config"
    root.mkdir()
    target = tmp_path / "target"
    target.write_text("valid")
    if symlink:
        (root / entry).symlink_to(target)
    else:
        (root / entry).write_text("valid")
    if pending:
        promotion_marker_path(root).write_text("pending\n")
    module = (REPO_ROOT / "modules/firewall.nix").read_text()
    script = module.split(
        "bootstrapWanToggle = pkgs.writeShellScript \"bootstrap-wan-toggle\" ''"
    )[1]
    script = script.split("  '';")[0]
    script = script.replace("/data/config", str(root)).replace("${cfg.wanInterface}", "eth0")
    fake_nft = 'nft() { if [ "$1" = add ]; then printf "open"; fi; }\n'
    result = subprocess.run(["bash", "-c", fake_nft + script], capture_output=True, check=True)
    assert (result.stdout == b"open") is open_wan
