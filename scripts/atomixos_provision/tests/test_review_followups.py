"""Regression coverage for worker blocking and committed-apply follow-ups."""

import hashlib
import os
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from atomixos_provision import provision, staging
from atomixos_provision.apply_transaction import StagedApplyTransaction
from atomixos_provision.config import ProvisionError
from atomixos_provision.quadlet import managed_files_are_writable, render_containers


def test_staged_request_rejects_fifo_swapped_before_hash_open(tmp_path, monkeypatch):
    """A raced-in FIFO must be opened nonblocking and rejected by fstat."""
    request = tmp_path / "request.bin"
    request.write_bytes(b"x")
    request.chmod(0o600)
    original_open = os.open

    def replace_before_open(path, flags, *args, **kwargs):
        if path == request:
            request.unlink()
            os.mkfifo(request, 0o600)
            # Fail safely on the old implementation rather than hanging the test.
            assert flags & os.O_NONBLOCK
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(staging.os, "open", replace_before_open)
    with pytest.raises(ProvisionError, match="must be a regular file"):
        staging._verify_staged_request(
            tmp_path,
            {"size": 1, "sha256": hashlib.sha256(b"x").hexdigest()},
            os.getuid(),
            os.getgid(),
        )


def test_stop_timeout_covers_supported_rollback_activation():
    """ExecStopPost receives the maximum activation budget plus recovery overhead."""
    root = Path(__file__).resolve().parents[3]
    module = (root / "modules/first-boot.nix").read_text()
    worker = module.split("systemd.services.atomixos-provision-apply = {")[1]
    worker = worker.split("systemd.services.quadlet-sync = {")[0]
    assert "TimeoutStopSec = 3900;" in worker


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


@pytest.mark.parametrize("transport", ["network", "nixstasis"])
def test_committed_finalizer_retries_rebind_before_result(tmp_path, monkeypatch, transport):
    """Recovery replays the durable committed follow-up before publishing success."""
    root = tmp_path / "config"
    root.mkdir()
    (root / "config.toml").write_text("already committed config\n")
    result = {"reapply": True, "forwarding_url": "http://10.44.0.1:8080", "warnings": []}
    manifest = {"job_id": "job-1", "source_sha256": "a" * 64}
    transaction = StagedApplyTransaction.from_manifest(manifest, result)
    transaction.mark_promoted(root)
    transaction.mark_committed(root)
    receipt_before = (root / ".atomixos-apply-receipt.json").read_bytes()
    paths = staging.runtime_paths(tmp_path / "run")
    staging.ensure_runtime_layout(paths, for_worker=True)
    active = paths.active / "job-1"
    active.mkdir()
    staging.write_json_atomic(active / "manifest.json", manifest)
    monkeypatch.setenv("ATOMIXOS_BOOTSTRAP_TRANSPORT", transport)
    monkeypatch.setattr(provision, "validate_config_root", lambda value, **_: value)
    calls = []

    def schedule(command, **_kwargs):
        if not calls:
            assert staging.read_result(paths, "job-1") is None
        calls.append(command)
        # A repeated request may find the same timer already queued.
        return CompletedProcess(command, 0 if len(calls) == 1 else 1)

    monkeypatch.setattr(provision.subprocess, "run", schedule)
    assert provision.finalize_staged_jobs(root, paths.root) == 1
    published = staging.read_result(paths, "job-1")
    assert published["status"] == "succeeded"
    assert published["result"] == result
    assert provision.finalize_staged_jobs(root, paths.root) == 0
    assert (root / ".atomixos-apply-receipt.json").read_bytes() == receipt_before
    if transport == "network":
        assert len(calls) == 2
        assert calls[0] == calls[1]
        assert "--unit=atomixos-bootstrap-rebind-delayed" in calls[0]
        assert "--collect" in calls[0]
    else:
        assert calls == []
    calls.clear()
    provision._recover_staged_apply(root, boot_recovery=True)
    assert calls == []
