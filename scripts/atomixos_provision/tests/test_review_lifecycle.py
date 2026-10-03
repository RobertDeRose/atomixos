"""Regression tests for reviewed recovery, monitoring, and deployment contracts."""

import asyncio
import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from atomixos_provision import provision, server
from atomixos_provision.activation import promotion_marker_path, rollback_root_path
from atomixos_provision.apply_transaction import StagedApplyTransaction
from atomixos_provision.jobs import Job, JobState, StagedJobManager
from atomixos_provision.quadlet import managed_files_are_writable, render_containers
from atomixos_provision.staging import (
    StagedTimeoutState,
    ensure_runtime_layout,
    read_result,
    runtime_paths,
    write_json_atomic,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_boot_recovery_does_not_wait_for_ordered_wan_unit(tmp_path, monkeypatch):
    """Boot recovery leaves WAN reconciliation to the service ordered after it."""
    root = tmp_path / "config"
    root.mkdir()
    (root / "config.toml").write_text("version = 1\n")
    StagedApplyTransaction.from_manifest(
        {"job_id": "job-1", "source_sha256": "a" * 64}, {"reapply": False}
    ).mark_promoted(root)
    calls = []
    monkeypatch.setenv("ATOMIXOS_BOOTSTRAP_TRANSPORT", "network")
    monkeypatch.setattr(provision, "reconcile_bootstrap_wan", lambda: calls.append("WAN"))

    result = CliRunner().invoke(server.cli, ["recover", str(root)])

    assert result.exit_code == 0, result.exception
    assert not root.exists()
    assert calls == []


@pytest.mark.parametrize("activation_errors", [[], ["rollback activation failed"]])
def test_finalizer_merges_users_and_activates_before_result(
    tmp_path, monkeypatch, activation_errors
):
    """Same-boot recovery reconciles restored runtime state before publishing failure."""
    root = tmp_path / "config"
    root.mkdir()
    (root / "config.toml").write_text("new")
    (root / "managed-users.json").write_text('["new-user"]')
    rollback = rollback_root_path(root)
    rollback.mkdir()
    (rollback / "config.toml").write_text("old")
    (rollback / "managed-users.json").write_text('["old-user"]')
    promotion_marker_path(root).write_text("pending\n")
    StagedApplyTransaction.from_manifest(
        {"job_id": "job-1", "source_sha256": "a" * 64}, {"reapply": True}
    ).mark_promoted(root)
    paths = runtime_paths(tmp_path / "run")
    ensure_runtime_layout(paths, for_worker=True)
    (paths.active / "job-1").mkdir()
    write_json_atomic(
        paths.active / "job-1" / "manifest.json",
        {"job_id": "job-1", "source_sha256": "a" * 64},
    )
    monkeypatch.setattr(provision, "validate_config_root", lambda value, **_: value)
    calls = []

    def activate(restored_root, progress=None):
        assert (restored_root / "config.toml").read_text() == "old"
        assert set(json.loads((restored_root / "managed-users.json").read_text())) == {
            "new-user",
            "old-user",
        }
        assert read_result(paths, "job-1") is None
        calls.append("activate")
        return activation_errors

    monkeypatch.setattr(provision, "run_activation_sequence", activate, raising=False)
    assert provision.finalize_staged_jobs(root, paths.root, "worker stopped") == 1
    assert calls == ["activate"]
    result = read_result(paths, "job-1")
    assert result["status"] == "failed"
    if activation_errors:
        assert "rollback activation failed" in result["error"]


@pytest.mark.asyncio
async def test_monitor_retries_result_io_errors_without_terminal_failure(monkeypatch):
    """A claimed job remains active when its result cannot temporarily be read."""
    manager = StagedJobManager(result_timeout_seconds=0)
    job = Job(id="job-1", state=JobState.RUNNING)
    release = asyncio.Event()
    calls = 0

    def refresh(current):
        nonlocal calls
        calls += 1
        if not release.is_set():
            raise PermissionError("result temporarily unreadable")
        current.state = JobState.SUCCEEDED
        return True

    monkeypatch.setattr(manager, "_refresh_from_result", refresh)
    monkeypatch.setattr(manager, "_handle_staged_timeout", lambda _: StagedTimeoutState.CLAIMED)
    task = asyncio.create_task(manager._monitor_staged(job))
    await asyncio.sleep(0.45)
    try:
        assert job.state is JobState.RUNNING
        assert job.completed_at is None
        assert sum("retry" in event.get("message", "") for event in job.events) == 1
    finally:
        release.set()
        await task
    assert calls >= 2
    assert job.state is JobState.SUCCEEDED


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


def test_worker_tools_and_finalizer_environment():
    """Worker signatures and finalization use their required pinned executables."""
    module = (REPO_ROOT / "modules/first-boot.nix").read_text()
    worker = module.split("systemd.services.atomixos-provision-apply = {")[1]
    worker = worker.split("systemd.services.quadlet-sync = {")[0]
    assert "pkgs.openssh" in worker or "ATOMIXOS_SSH_KEYGEN" in worker
    finalizer = module.split("provisionApplyFinalizeScript = pkgs.writeShellScript")[1]
    finalizer = finalizer.split("  '';")[0]
    assert "ATOMIXOS_BOOTSTRAP_ACTIVATION" in finalizer
