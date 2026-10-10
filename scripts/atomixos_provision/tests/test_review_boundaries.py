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


def _nested_tree(root, depth):
    """Create ``depth`` nested directories below root and return the deepest one."""
    current = root
    for _ in range(depth):
        current = current / "d"
        current.mkdir()
    return current


def _mock_managed_identity(monkeypatch):
    """Resolve managed-file identities without requiring host accounts."""
    monkeypatch.setattr(
        bundle.pwd, "getpwnam", lambda _name: type("Pw", (), {"pw_uid": os.getuid()})()
    )
    monkeypatch.setattr(
        bundle.grp, "getgrnam", lambda _name: type("Gr", (), {"gr_gid": os.getgid()})()
    )
    monkeypatch.setattr(bundle.os, "fchown", lambda *_args: None)


@pytest.mark.parametrize("operation", ["snapshot", "reconciliation"])
@pytest.mark.parametrize("extra_depth", [0, 1])
def test_traversal_bounds_directory_depth(tmp_path, monkeypatch, operation, extra_depth):
    """Fail deep trees with a provisioning error before exhausting stack or descriptors."""
    _mock_managed_identity(monkeypatch)
    root = tmp_path / "files"
    root.mkdir()
    (_nested_tree(root, bundle.MAX_BUNDLE_DEPTH + extra_depth) / "payload").write_text("x")

    def traverse():
        """Run the selected recursive walker over the nested tree."""
        if operation == "snapshot":
            bundle._snapshot_files_source(root, tmp_path / "snapshot")
        else:
            bundle.grant_managed_file_access(root, writable=True)

    if extra_depth:
        with pytest.raises(ProvisionError, match="directory depth limit"):
            traverse()
    else:
        traverse()


def test_read_only_acl_encodes_named_appsvc_entry():
    """Encode the Linux xattr ACL with owner, appsvc, group, mask, and no other access."""
    import struct

    encoded = bundle._read_only_access_acl(1234, 0o4)

    assert struct.unpack("<I", encoded[:4]) == (2,)
    entries = [struct.unpack("<HHI", encoded[i : i + 8]) for i in range(4, len(encoded), 8)]
    undefined = 0xFFFFFFFF
    assert entries == [
        (0x01, 0o4, undefined),
        (0x02, 0o4, 1234),
        (0x04, 0o4, undefined),
        (0x10, 0o4, undefined),
        (0x20, 0, undefined),
    ]


def test_read_only_acl_fails_closed_without_filesystem_support(tmp_path, monkeypatch):
    """Refuse to leave read-only inputs unreadable or unprotected when ACLs fail."""
    import errno

    set_access_acl = bundle._set_access_acl.__wrapped__
    target = tmp_path / "payload"
    target.write_text("x")

    def unsupported(*_args):
        raise OSError(errno.EOPNOTSUPP, "Operation not supported")

    monkeypatch.setattr(bundle.os, "setxattr", unsupported, raising=False)
    fd = os.open(target, os.O_RDONLY)
    try:
        with pytest.raises(ProvisionError, match="must support POSIX ACLs"):
            set_access_acl(fd, 1234, 0o4, target)
    finally:
        os.close(fd)


@pytest.mark.skipif(not hasattr(os, "setxattr"), reason="requires Linux xattrs")
def test_read_only_acl_round_trips_through_kernel(tmp_path):
    """The kernel accepts the encoded ACL and clearing it restores plain modes."""
    import errno

    target = tmp_path / "payload"
    target.write_text("x")
    fd = os.open(target, os.O_RDONLY)
    try:
        try:
            bundle._set_access_acl.__wrapped__(fd, os.getuid() + 1, 0o4, target)
        except ProvisionError:
            pytest.skip("test filesystem lacks POSIX ACL support")
        stored = os.getxattr(fd, bundle.ACL_ACCESS_XATTR)
        assert stored == bundle._read_only_access_acl(os.getuid() + 1, 0o4)
        assert os.fstat(fd).st_mode & 0o777 == 0o440
        bundle._clear_access_acl(fd)
        with pytest.raises(OSError) as missing:
            os.getxattr(fd, bundle.ACL_ACCESS_XATTR)
        assert missing.value.errno == errno.ENODATA
    finally:
        os.close(fd)
