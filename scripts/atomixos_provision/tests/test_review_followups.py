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


def test_staged_snapshot_rejects_fifo_swapped_before_copy_open(tmp_path, monkeypatch):
    """Snapshot copies reject raced special files without waiting for a writer."""
    source = tmp_path / "staged.txt"
    source.write_bytes(b"x")
    destination = tmp_path / "snapshot.txt"
    original_open = os.open

    def replace_before_open(path, flags, *args, **kwargs):
        if path == source:
            source.unlink()
            os.mkfifo(source, 0o600)
            # Fail safely on the old implementation rather than hanging the test.
            assert flags & os.O_NONBLOCK
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(provision.os, "open", replace_before_open)
    with pytest.raises(ProvisionError, match="must be a regular file"):
        provision._copy_staged_file_from_path(source, destination, expected_size=1)
    assert not destination.exists()


def test_fifo_ready_marker_does_not_block_next_job(tmp_path, monkeypatch):
    """Queue scanning rejects a FIFO control file and admits the next valid job."""
    paths = staging.runtime_paths(tmp_path / "run")
    staging.ensure_runtime_layout(paths, for_worker=True)
    bad_marker = paths.queue / "bad.ready"
    os.mkfifo(bad_marker, 0o600)
    (paths.queue / "job-1").mkdir()
    staging.write_json_atomic(paths.queue / "job-1.ready", {"sequence": 1})
    original_open = os.open

    def nonblocking_open(path, flags, *args, **kwargs):
        if path == bad_marker:
            # Fail safely on the old implementation rather than hanging the test.
            assert flags & os.O_NONBLOCK
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(staging.os, "open", nonblocking_open)
    claimed = staging.claim_next_job(paths)
    assert claimed is not None
    assert claimed.job_id == "job-1"
    assert not bad_marker.exists()


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
@pytest.mark.parametrize("reapply", [False, True])
def test_committed_finalizer_retries_transport_followup_before_result(
    tmp_path, monkeypatch, transport, reapply
):
    """Recovery replays the durable committed follow-up before publishing success."""
    root = tmp_path / "config"
    root.mkdir()
    (root / "config.toml").write_text("already committed config\n")
    result = {"reapply": reapply, "forwarding_url": "http://10.44.0.1:8080", "warnings": []}
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
        return CompletedProcess(command, 0)

    monkeypatch.setattr(provision.subprocess, "run", schedule)
    assert provision.finalize_staged_jobs(root, paths.root) == 1
    published = staging.read_result(paths, "job-1")
    assert published["status"] == "succeeded"
    assert published["result"] == result
    assert provision.finalize_staged_jobs(root, paths.root) == 0
    assert (root / ".atomixos-apply-receipt.json").read_bytes() == receipt_before
    if transport == "network":
        assert len(calls) == 1
        if reapply:
            assert "--unit=atomixos-bootstrap-rebind-delayed" in calls[0]
            assert "--collect" in calls[0]
        else:
            assert calls[0] == ["systemctl", "restart", "bootstrap-wan-toggle.service"]
    else:
        assert calls == []
    calls.clear()
    # Result acknowledgement or expiry must not make a completed receipt unfinished.
    (paths.results / "job-1.json").unlink()
    assert provision.finalize_staged_jobs(root, paths.root) == 0
    assert calls == []
    provision._recover_staged_apply(root, boot_recovery=True)
    assert calls == []


@pytest.mark.parametrize("reapply", [False, True])
@pytest.mark.parametrize("job_state", ["published", "wrong_digest", "wrong_job", "symlink"])
def test_finalizer_skips_committed_followups_without_unfinished_matching_claim(
    tmp_path, monkeypatch, reapply, job_state
):
    """Published results and mismatched claims cannot replay old transport changes."""
    root = tmp_path / "config"
    root.mkdir()
    result = {"reapply": reapply, "forwarding_url": "http://10.44.0.1:8080"}
    manifest = {"job_id": "job-1", "source_sha256": "a" * 64}
    transaction = StagedApplyTransaction.from_manifest(manifest, result)
    transaction.mark_promoted(root)
    transaction.mark_committed(root)
    paths = staging.runtime_paths(tmp_path / "run")
    staging.ensure_runtime_layout(paths, for_worker=True)
    active = paths.active / "job-1"
    if job_state == "symlink":
        target = tmp_path / "other-job"
        target.mkdir()
        active.symlink_to(target, target_is_directory=True)
    else:
        active.mkdir()
    if job_state == "wrong_digest":
        manifest["source_sha256"] = "b" * 64
    elif job_state == "wrong_job":
        manifest["job_id"] = "job-2"
    staging.write_json_atomic(active / "manifest.json", manifest)
    published = {"status": "succeeded", "result": result}
    if job_state == "published":
        staging.write_result(paths, "job-1", published)
        published = staging.read_result(paths, "job-1")
    monkeypatch.setenv("ATOMIXOS_BOOTSTRAP_TRANSPORT", "network")
    monkeypatch.setattr(provision, "validate_config_root", lambda value, **_: value)
    calls = []
    monkeypatch.setattr(provision.subprocess, "run", lambda command, **_: calls.append(command))

    assert provision.finalize_staged_jobs(root, paths.root) == (0 if job_state == "symlink" else 1)
    assert calls == []
    assert not active.exists()
    if job_state == "published":
        assert staging.read_result(paths, "job-1") == published
    elif job_state == "symlink":
        assert staging.read_result(paths, "job-1") is None
        assert target.is_dir()
    else:
        assert staging.read_result(paths, "job-1")["status"] == "failed"


@pytest.mark.parametrize("reapply", [False, True])
def test_unrelated_worker_failure_does_not_replay_completed_followups(
    tmp_path, monkeypatch, reapply
):
    """Rejecting a later job does not reconcile transport for a previous receipt."""
    root = tmp_path / "config"
    root.mkdir()
    transaction = StagedApplyTransaction.from_manifest(
        {"job_id": "job-1", "source_sha256": "a" * 64},
        {"reapply": reapply, "forwarding_url": "http://10.44.0.1:8080"},
    )
    transaction.mark_promoted(root)
    transaction.mark_committed(root)
    paths = staging.runtime_paths(tmp_path / "run")
    staging.ensure_runtime_layout(paths, for_worker=True)
    (paths.queue / "job-2").mkdir()
    staging.write_json_atomic(paths.queue / "job-2.ready", {"sequence": 1})
    monkeypatch.setenv("ATOMIXOS_BOOTSTRAP_TRANSPORT", "network")
    monkeypatch.setattr(provision, "validate_config_root", lambda value, **_: value)

    def reject_job(*_args, **_kwargs):
        raise ProvisionError("invalid staged job")

    monkeypatch.setattr(provision, "verify_staged_job", reject_job)
    calls = []
    monkeypatch.setattr(provision.subprocess, "run", lambda command, **_: calls.append(command))
    with pytest.raises(ProvisionError, match="invalid staged job"):
        provision.apply_staged_job(root, paths.root)

    assert staging.read_result(paths, "job-2")["status"] == "failed"
    assert calls == []
