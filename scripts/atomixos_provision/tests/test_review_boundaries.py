"""Regression coverage for PR review privilege and resource boundaries."""

import os

import pytest

from atomixos_provision import bundle
from atomixos_provision.config import ProvisionError


@pytest.mark.parametrize("entry_kind", ["file", "directory"])
def test_permission_reconciliation_rejects_replaced_symlink(tmp_path, monkeypatch, entry_kind):
    """Replacing a checked child cannot redirect privileged permission changes."""
    root = tmp_path / "files"
    root.mkdir()
    child = root / "child"
    target = tmp_path / "target"
    if entry_kind == "directory":
        child.mkdir()
        target.mkdir()
        (target / "secret").write_text("secret")
    else:
        child.write_text("payload")
        target.write_text("secret")
    target.chmod(0o700)
    original_stat = os.stat

    def replacing_stat(path, *args, **kwargs):
        result = original_stat(path, *args, **kwargs)
        if path == "child" and kwargs.get("dir_fd") is not None:
            child.rmdir() if entry_kind == "directory" else child.unlink()
            child.symlink_to(target, target_is_directory=entry_kind == "directory")
        return result

    monkeypatch.setattr(bundle.os, "stat", replacing_stat)
    monkeypatch.setattr(bundle.os, "chown", lambda *args, **kwargs: None)
    monkeypatch.setattr(bundle.os, "fchown", lambda *args: None)
    with pytest.raises((ProvisionError, OSError)):
        bundle._grant_managed_file_access(root, os.getuid(), os.getgid())
    assert target.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("limit_kind", ["member", "total"])
def test_snapshot_stops_growing_source_before_writing_over_limit(
    tmp_path, monkeypatch, limit_kind
):
    """Size checks bound streamed writes even when a source grows after stat."""
    source = tmp_path / "source"
    source.mkdir()
    payload = source / "payload"
    payload.write_bytes(b"x")
    destination = tmp_path / "snapshot"
    original_fdopen = os.fdopen

    def growing_fdopen(fd, *args, **kwargs):
        payload.write_bytes(b"x" * 100)
        return original_fdopen(fd, *args, **kwargs)

    monkeypatch.setattr(bundle.os, "fdopen", growing_fdopen)
    with pytest.raises(ProvisionError, match=r"exceeds .* byte"):
        bundle._snapshot_files_source(
            source,
            destination,
            max_file_bytes=8 if limit_kind == "member" else None,
            max_total_bytes=8 if limit_kind == "total" else None,
        )
    assert (destination / "payload").stat().st_size <= 8
