"""Regression coverage for worker blocking and committed-apply follow-ups."""

import hashlib
import os
from pathlib import Path

import pytest

from atomixos_provision import provision, staging
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
