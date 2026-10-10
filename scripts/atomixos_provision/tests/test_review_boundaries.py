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
        """Replace the checked child after its initial metadata lookup."""
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
        """Grow the source after its initial stat and before the read begins."""
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


@pytest.mark.parametrize(
    ("mutation_kind", "error_pattern"),
    [
        ("metadata", r"bundle file changed during snapshot"),
        ("truncate", r"bundle file size changed during snapshot"),
    ],
)
def test_snapshot_rejects_source_mutation_during_stream(
    tmp_path, monkeypatch, mutation_kind, error_pattern
):
    """Revalidate source metadata and copied size after streaming its open descriptor."""
    source = tmp_path / "source"
    source.mkdir()
    payload = source / "payload"
    payload_size = 128 * 1024
    payload.write_bytes(b"x" * payload_size)
    destination = tmp_path / "snapshot"
    original_fdopen = os.fdopen
    mutation_seen: list[bool] = []

    class MutatingReader:
        def __init__(self, wrapped):
            """Retain the underlying reader to inject a mutation after reads."""
            self.wrapped = wrapped

        def __enter__(self):
            """Enter the wrapped file context and return this reader."""
            self.wrapped.__enter__()
            return self

        def __exit__(self, *args):
            """Exit the wrapped file context."""
            return self.wrapped.__exit__(*args)

        def fileno(self):
            """Expose the open descriptor for final metadata validation."""
            return self.wrapped.fileno()

        def read(self, size=-1):
            """Read bytes, then mutate the source once to simulate a writer race."""
            chunk = self.wrapped.read(size)
            if chunk and not mutation_seen:
                mutation_seen.append(True)
                if mutation_kind == "metadata":
                    initial = payload.stat()
                    payload.write_bytes(b"y" * payload_size)
                    os.utime(
                        payload,
                        ns=(initial.st_atime_ns, initial.st_mtime_ns + 1_000_000),
                    )
                else:
                    with payload.open("r+b") as changed:
                        changed.truncate(1)
            return chunk

    def mutating_fdopen(fd, *args, **kwargs):
        """Wrap the source descriptor with a reader that mutates its file."""
        return MutatingReader(original_fdopen(fd, *args, **kwargs))

    monkeypatch.setattr(bundle.os, "fdopen", mutating_fdopen)
    with pytest.raises(ProvisionError, match=error_pattern):
        bundle._snapshot_files_source(source, destination)
    assert mutation_seen == [True]


@pytest.mark.parametrize("mutation_kind", ["create", "delete", "rename"])
def test_snapshot_rejects_directory_entry_mutation(tmp_path, monkeypatch, mutation_kind):
    """Reject entry changes made after a directory's names were enumerated."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "a").mkdir()
    (source / "b").mkdir()
    destination = tmp_path / "snapshot"
    original_stat = os.stat
    mutation_seen: list[bool] = []

    def mutating_stat(path, *args, **kwargs):
        """Mutate the enumerated directory before its last entry is copied."""
        if path == "b" and kwargs.get("dir_fd") is not None and not mutation_seen:
            mutation_seen.append(True)
            if mutation_kind == "create":
                (source / "c").mkdir()
            elif mutation_kind == "delete":
                (source / "a").rmdir()
            else:
                (source / "a").rename(source / "c")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(bundle.os, "stat", mutating_stat)
    with pytest.raises(ProvisionError, match=r"bundle directory changed during snapshot"):
        bundle._snapshot_files_source(source, destination)
    assert mutation_seen == [True]
