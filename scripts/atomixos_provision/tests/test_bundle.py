"""Tests for atomixos_provision.bundle module."""

import gzip
import io
import os
import tarfile
from pathlib import Path

import pytest

from atomixos_provision.bundle import (
    copy_bundle_files,
    detect_bundle_kind,
    export_bundle_bytes,
    extract_bundle_archive,
    grant_managed_file_access,
    prepare_source_bytes,
    prepare_source_path,
    stage_bundle_files,
    validate_bundle_layout,
    validate_bundle_member,
    validate_source_size,
)
from atomixos_provision.config import ProvisionError


class TestDetectBundleKind:
    def test_gzip_magic(self):
        assert detect_bundle_kind(b"\x1f\x8b" + b"rest") == "tar.gz"

    def test_zstd_magic(self):
        assert detect_bundle_kind(b"\x28\xb5\x2f\xfd" + b"rest") == "tar.zst"

    def test_filename_tgz(self):
        assert detect_bundle_kind(b"data", "config.tgz") == "tar.gz"

    def test_filename_tar_zstd(self):
        assert detect_bundle_kind(b"data", "config.tar.zstd") == "tar.zst"

    def test_unknown(self):
        assert detect_bundle_kind(b"plain text", "config.toml") is None


class TestValidateBundleMember:
    def test_valid(self):
        validate_bundle_member("config.toml")
        validate_bundle_member("files/cert.pem")

    def test_absolute_path(self):
        with pytest.raises(ProvisionError, match="invalid bundle member"):
            validate_bundle_member("/etc/passwd")

    def test_traversal(self):
        with pytest.raises(ProvisionError, match="invalid bundle member"):
            validate_bundle_member("../escape")

    def test_empty(self):
        with pytest.raises(ProvisionError, match="invalid bundle member"):
            validate_bundle_member("")


class TestValidateBundleLayout:
    def test_valid(self, tmp_path):
        (tmp_path / "config.toml").write_text("version = 1")
        (tmp_path / "files").mkdir()
        validate_bundle_layout(tmp_path)

    def test_missing_config(self, tmp_path):
        (tmp_path / "files").mkdir()
        with pytest.raises(ProvisionError, match=r"must contain config\.toml"):
            validate_bundle_layout(tmp_path)

    def test_unexpected_entry(self, tmp_path):
        (tmp_path / "config.toml").write_text("")
        (tmp_path / "extra.txt").write_text("")
        with pytest.raises(ProvisionError, match="unsupported top-level"):
            validate_bundle_layout(tmp_path)


class TestExtractBundleArchive:
    def _make_tar_gz(self, content: dict[str, str]) -> bytes:
        """Create a tar.gz bytes object from {filename: content} dict."""
        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w:") as tar:
            for name, data in content.items():
                info = tarfile.TarInfo(name=name)
                encoded = data.encode()
                info.size = len(encoded)
                tar.addfile(info, io.BytesIO(encoded))
        return gzip.compress(tar_buf.getvalue())

    def test_extract_tar_gz(self, tmp_path):
        bundle = self._make_tar_gz({"config.toml": "version = 1"})
        extract_bundle_archive(bundle, "test.tar.gz", tmp_path)
        assert (tmp_path / "config.toml").read_text() == "version = 1"

    def test_malformed_tar_gz_reports_provision_error(self, tmp_path):
        with pytest.raises(ProvisionError, match="failed to read bundle archive"):
            extract_bundle_archive(gzip.compress(b"not a tar archive"), "test.tar.gz", tmp_path)

    def test_unsupported_format(self, tmp_path):
        with pytest.raises(ProvisionError, match="supported bundle formats"):
            extract_bundle_archive(b"plain text", "unknown.bin", tmp_path)

    def test_rejects_oversized_member(self, tmp_path, monkeypatch):
        import atomixos_provision.bundle as bundle_module

        monkeypatch.setattr(bundle_module, "MAX_BUNDLE_MEMBER_BYTES", 1)
        bundle = self._make_tar_gz({"config.toml": "version = 1"})
        with pytest.raises(ProvisionError, match=r"exceeds .* byte limit"):
            extract_bundle_archive(bundle, "test.tar.gz", tmp_path)

    def test_member_limit_stops_reading_headers(self, tmp_path, monkeypatch):
        """Reject an oversized archive without holding every tar header in memory."""
        import atomixos_provision.bundle as bundle_module

        monkeypatch.setattr(bundle_module, "MAX_BUNDLE_MEMBERS", 3)
        headers_read = []
        original_next = tarfile.TarFile.next

        def counting_next(archive):
            """Count each header the extractor pulls from the archive."""
            member = original_next(archive)
            if member is not None:
                headers_read.append(member.name)
            return member

        monkeypatch.setattr(tarfile.TarFile, "next", counting_next)
        bundle = self._make_tar_gz({f"files/{index}": "" for index in range(50)})

        with pytest.raises(ProvisionError, match="bundle exceeds 3 member limit"):
            extract_bundle_archive(bundle, "test.tar.gz", tmp_path)
        # tarfile.open reads the first header once to validate the archive.
        assert sorted(set(headers_read)) == ["files/0", "files/1", "files/2", "files/3"]
        assert list(tmp_path.iterdir()) == []

    def test_rejects_sparse_member_before_writing(self, tmp_path):
        """A tiny archive cannot declare a large sparse member to fill temporary storage."""
        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w:", format=tarfile.PAX_FORMAT) as tar:
            tar.addfile(tarfile.TarInfo("config.toml"), io.BytesIO())
            # A PAX 1.0 GNU sparse member: a one-block map expands to realsize zeros.
            info = tarfile.TarInfo("GNUSparseFile.0/files/big")
            info.size = 512
            info.pax_headers = {
                "GNU.sparse.major": "1",
                "GNU.sparse.minor": "0",
                "GNU.sparse.name": "files/big",
                "GNU.sparse.realsize": str(64 * 1024 * 1024),
            }
            tar.addfile(info, io.BytesIO(b"1\n0\n0\n".ljust(512, b"\0")))

        with pytest.raises(ProvisionError, match="sparse bundle member is not supported"):
            extract_bundle_archive(gzip.compress(tar_buf.getvalue()), "test.tar.gz", tmp_path)
        assert list(tmp_path.iterdir()) == []

    def test_rejects_cumulative_member_size_before_writing(self, tmp_path, monkeypatch):
        """Bound the extracted tree by summed tar headers, not only the decompressed stream."""
        import atomixos_provision.bundle as bundle_module

        decompress = bundle_module._decompress_to_tempfile

        def decompress_then_lower_limit(*args):
            """Allow the stream through, then shrink the budget for the header check."""
            path = decompress(*args)
            monkeypatch.setattr(bundle_module, "MAX_DECOMPRESSED_BYTES", 15)
            return path

        monkeypatch.setattr(bundle_module, "_decompress_to_tempfile", decompress_then_lower_limit)
        bundle = self._make_tar_gz({"config.toml": "version = 1", "files/a": "123456"})
        with pytest.raises(ProvisionError, match="15 byte decompressed limit"):
            extract_bundle_archive(bundle, "test.tar.gz", tmp_path)
        assert list(tmp_path.iterdir()) == []


class TestValidateSourceSize:
    def test_rejects_large_source(self, monkeypatch):
        import atomixos_provision.bundle as bundle_module

        monkeypatch.setattr(bundle_module, "MAX_SOURCE_BYTES", 1)
        with pytest.raises(ProvisionError, match="config upload exceeds"):
            validate_source_size(b"too large")


class TestCopyBundleFiles:
    """Group tests for CopyBundleFiles."""

    def _mock_appsvc(self, monkeypatch):
        """Handle mock appsvc."""
        chowns: list[tuple[str, int, int]] = []
        monkeypatch.setattr(
            "atomixos_provision.bundle.pwd.getpwnam",
            lambda _name: type("Pw", (), {"pw_uid": 1000, "pw_gid": 1000})(),
        )
        monkeypatch.setattr(
            "atomixos_provision.bundle.grp.getgrnam",
            lambda _name: type("Gr", (), {"gr_gid": 2000})(),
        )
        monkeypatch.setattr(
            "atomixos_provision.bundle.os.chown",
            lambda path, uid, gid, **_kwargs: chowns.append((str(path), uid, gid)),
        )
        monkeypatch.setattr(
            "atomixos_provision.bundle.os.fchown",
            lambda fd, uid, gid: chowns.append((f"fd:{fd}", uid, gid)),
        )
        return chowns

    def test_copies_files(self, tmp_path, monkeypatch, managed_acl_calls):
        """Install read-only copies as root-owned with appsvc ACL read access."""
        chowns = self._mock_appsvc(monkeypatch)
        source = tmp_path / "source_files"
        source.mkdir()
        (source / "cert.pem").write_text("CERT")
        sub = source / "subdir"
        sub.mkdir()
        (sub / "key.pem").write_text("KEY")

        config_root = tmp_path / "config"
        config_root.mkdir()
        copy_bundle_files(source, config_root)

        assert (config_root / "files" / "cert.pem").read_text() == "CERT"
        assert (config_root / "files" / "subdir" / "key.pem").read_text() == "KEY"
        assert (config_root / "files").stat().st_mode & 0o777 == 0o550
        assert (config_root / "files" / "subdir").stat().st_mode & 0o777 == 0o550
        assert (config_root / "files" / "cert.pem").stat().st_mode & 0o777 == 0o440
        assert (config_root / "files" / "subdir" / "key.pem").stat().st_mode & 0o777 == 0o440
        assert sum(path.startswith("fd:") for path, _uid, _gid in chowns) == 4
        assert all((uid, gid) == (0, 2000) for _path, uid, gid in chowns)
        assert sorted((uid, perm) for uid, perm, _path in managed_acl_calls) == [
            (1000, 0o4),
            (1000, 0o4),
            (1000, 0o5),
            (1000, 0o5),
        ]

    def test_read_only_reconciliation_removes_workload_ownership(
        self, tmp_path, monkeypatch, managed_acl_calls
    ):
        """A writable tree becomes root-owned with ACL reads when mounts turn read-only."""
        import atomixos_provision.bundle as bundle_module

        chowns = self._mock_appsvc(monkeypatch)
        cleared: list[int] = []
        monkeypatch.setattr(bundle_module, "_clear_access_acl", cleared.append)
        files_root = tmp_path / "files"
        files_root.mkdir()
        (files_root / "state.json").write_text("{}\n")

        grant_managed_file_access(files_root, writable=True)
        assert [(uid, gid) for _path, uid, gid in chowns] == [(1000, 2000), (1000, 2000)]
        assert len(cleared) == 2
        assert managed_acl_calls == []

        chowns.clear()
        grant_managed_file_access(files_root)

        assert [(uid, gid) for _path, uid, gid in chowns] == [(0, 2000), (0, 2000)]
        assert files_root.stat().st_mode & 0o777 == 0o550
        assert files_root.joinpath("state.json").stat().st_mode & 0o777 == 0o440
        assert [(uid, perm) for uid, perm, _path in managed_acl_calls] == [
            (1000, 0o5),
            (1000, 0o4),
        ]
        files_root.chmod(0o750)

    def test_reconciles_existing_files_for_writable_mount(self, tmp_path, monkeypatch):
        """Verify that recovery reconciliation preserves rootless writable access."""
        chowns = self._mock_appsvc(monkeypatch)
        files_root = tmp_path / "files"
        files_root.mkdir()
        (files_root / "state.json").write_text("{}\n")
        (files_root / "state.json").chmod(0o600)

        grant_managed_file_access(files_root, writable=True)

        assert files_root.stat().st_mode & 0o777 == 0o750
        assert len(chowns) == 2
        assert all((uid, gid) == (1000, 2000) for _path, uid, gid in chowns)
        assert files_root.joinpath("state.json").stat().st_mode & 0o777 == 0o640

    @pytest.mark.parametrize("entrypoint", ["existing", "staging"])
    def test_reconciliation_stops_enumerating_at_member_limit(
        self, tmp_path, monkeypatch, entrypoint
    ):
        """Stop a large directory before consuming or changing excess entries."""
        import atomixos_provision.bundle as bundle_module

        chowns = self._mock_appsvc(monkeypatch)
        root = tmp_path / "files"
        root.mkdir()
        for index in range(10):
            (root / f"entry-{index}").mkdir()
        monkeypatch.setattr(bundle_module, "MAX_BUNDLE_MEMBERS", 3)
        real_scandir = os.scandir
        seen = []
        closed = []

        class TrackingScandir:
            def __init__(self, fd):
                self.iterator = real_scandir(fd)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.iterator.close()
                closed.append(True)

            def __iter__(self):
                for entry in self.iterator:
                    seen.append(entry.name)
                    yield entry

        monkeypatch.setattr(bundle_module.os, "scandir", TrackingScandir)
        with pytest.raises(ProvisionError, match="bundle exceeds 3 member limit"):
            if entrypoint == "existing":
                grant_managed_file_access(root, writable=True)
            else:
                bundle_module._grant_managed_file_access(root, 1000, 2000, writable=True)

        assert len(seen) == 4
        assert len(chowns) == (4 if entrypoint == "existing" else 3)
        assert len(closed) == 4

    @pytest.mark.parametrize("limit", [2, 3])
    def test_reconciliation_counts_nested_members_globally(self, tmp_path, monkeypatch, limit):
        """Share one budget across sibling directories and accept its exact limit."""
        import atomixos_provision.bundle as bundle_module

        chowns = self._mock_appsvc(monkeypatch)
        root = tmp_path / "files"
        (root / "first" / "nested").mkdir(parents=True)
        (root / "second").mkdir()
        monkeypatch.setattr(bundle_module, "MAX_BUNDLE_MEMBERS", limit)

        if limit == 2:
            with pytest.raises(ProvisionError, match="bundle exceeds 2 member limit"):
                grant_managed_file_access(root, writable=True)
            assert len(chowns) == 3
        else:
            grant_managed_file_access(root, writable=True)
            assert len(chowns) == 4
            assert all(path.stat().st_mode & 0o777 == 0o750 for path in root.rglob("*"))

    def test_rejects_hardlinked_managed_file_before_chown_or_chmod(self, tmp_path, monkeypatch):
        """Reject hardlinks without mutating their external inode."""
        chowns = self._mock_appsvc(monkeypatch)
        chmods: list[tuple[int, int]] = []
        monkeypatch.setattr(
            "atomixos_provision.bundle.os.fchmod",
            lambda fd, mode: chmods.append((fd, mode)),
        )
        files_root = tmp_path / "files"
        files_root.mkdir()
        outside = tmp_path / "outside.json"
        outside.write_text("{}\n")
        outside_stat = outside.stat()
        (files_root / "state.json").hardlink_to(outside)

        with pytest.raises(ProvisionError, match="single-link regular file"):
            grant_managed_file_access(files_root)

        after_stat = outside.stat()
        assert (after_stat.st_uid, after_stat.st_gid, after_stat.st_mode) == (
            outside_stat.st_uid,
            outside_stat.st_gid,
            outside_stat.st_mode,
        )
        assert len(chowns) == 1
        assert len(chmods) == 1

    @pytest.mark.parametrize(
        ("limit_name", "limit", "pattern"),
        [
            ("MAX_BUNDLE_MEMBERS", 1, "bundle exceeds 1 member limit"),
            ("MAX_BUNDLE_MEMBER_BYTES", 2, "exceeds 2 byte limit"),
            ("MAX_DECOMPRESSED_BYTES", 5, "exceeds 5 byte decompressed limit"),
        ],
    )
    def test_stage_bundle_files_enforces_snapshot_limits(
        self, tmp_path, monkeypatch, limit_name, limit, pattern
    ):
        """Enforce configured member and byte limits during staging."""
        import atomixos_provision.bundle as bundle_module

        monkeypatch.setattr(bundle_module, "MAX_BUNDLE_MEMBERS", 100)
        monkeypatch.setattr(bundle_module, "MAX_BUNDLE_MEMBER_BYTES", 100)
        monkeypatch.setattr(bundle_module, "MAX_DECOMPRESSED_BYTES", 100)
        monkeypatch.setattr(bundle_module, limit_name, limit)
        source = tmp_path / "source-files"
        source.mkdir()
        (source / "first.txt").write_bytes(b"abc")
        (source / "second.txt").write_bytes(b"def")

        with pytest.raises(ProvisionError, match=pattern):
            stage_bundle_files(source, tmp_path / "destination")

    def test_snapshot_stops_enumerating_after_member_limit(self, tmp_path, monkeypatch):
        """Stop reading a directory once its global member limit is exceeded."""
        import atomixos_provision.bundle as bundle_module

        monkeypatch.setattr(bundle_module, "MAX_BUNDLE_MEMBERS", 1)
        source = tmp_path / "source-files"
        source.mkdir()
        for index in range(10):
            (source / f"entry-{index:02d}.txt").write_bytes(b"x")

        real_scandir = bundle_module.os.scandir
        seen: list[str] = []

        class TrackingScandir:
            def __init__(self, iterator):
                self.iterator = iterator

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                self.iterator.close()

            def __iter__(self):
                return self

            def __next__(self):
                entry = next(self.iterator)
                seen.append(entry.name)
                return entry

        def tracking_scandir(path):
            return TrackingScandir(real_scandir(path))

        monkeypatch.setattr(bundle_module.os, "scandir", tracking_scandir)

        with pytest.raises(ProvisionError, match="bundle exceeds 1 member limit"):
            stage_bundle_files(source, tmp_path / "destination")

        assert len(seen) == 2

    def test_snapshot_reserves_pending_ancestor_members(self, tmp_path, monkeypatch):
        """Keep pending ancestor names within the global enumeration budget."""
        import atomixos_provision.bundle as bundle_module

        source = tmp_path / "source"
        source.mkdir()
        nested = source / "a-directory"
        nested.mkdir()
        for index in range(3):
            (source / f"z-{index}").mkdir()
            (nested / f"entry-{index}").mkdir()
        monkeypatch.setattr(bundle_module, "MAX_BUNDLE_MEMBERS", 4)
        real_scandir = bundle_module.os.scandir
        seen = []

        class TrackingScandir:
            def __init__(self, iterator):
                self.iterator = iterator

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.iterator.close()

            def __iter__(self):
                for entry in self.iterator:
                    seen.append(entry.name)
                    yield entry

        monkeypatch.setattr(
            bundle_module.os, "scandir", lambda path: TrackingScandir(real_scandir(path))
        )
        with pytest.raises(ProvisionError, match="bundle exceeds 4 member limit"):
            stage_bundle_files(source, tmp_path / "destination")
        assert len(seen) == 5

    @pytest.mark.skipif(not hasattr(os, "O_PATH"), reason="requires Linux O_PATH")
    @pytest.mark.parametrize("operation", ["snapshot", "reconciliation"])
    @pytest.mark.parametrize("replacement", ["fifo", "regular"])
    def test_file_swap_never_opens_for_reading(
        self, tmp_path, monkeypatch, native_file_open, operation, replacement
    ):
        """Reject an unverified replacement before any readable open."""
        import atomixos_provision.bundle as bundle_module

        self._mock_appsvc(monkeypatch)
        source = tmp_path / "source"
        source.mkdir()
        payload = source / "payload"
        payload.write_bytes(b"data")
        real_open = bundle_module.os.open
        readable_opens = []
        swapped = False

        def swap_before_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == "payload" and not swapped:
                payload.rename(source / "retained")
                if replacement == "fifo":
                    os.mkfifo(payload)
                else:
                    payload.write_bytes(b"replacement")
                swapped = True
            if path == "payload" and not flags & os.O_PATH:
                readable_opens.append(path)
                pytest.fail("unverified replacement inode was opened for reading")
            return real_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(bundle_module.os, "open", swap_before_open)
        pattern = "single-link regular file" if replacement == "fifo" else "changed during"
        with pytest.raises(ProvisionError, match=pattern):
            if operation == "snapshot":
                stage_bundle_files(source, tmp_path / "destination")
            else:
                grant_managed_file_access(source, writable=True)
        assert swapped
        assert not readable_opens

    @pytest.mark.skipif(not hasattr(os, "O_PATH"), reason="requires Linux O_PATH")
    @pytest.mark.parametrize("operation", ["snapshot", "reconciliation"])
    def test_uses_pinned_inode_after_name_swap(
        self, tmp_path, monkeypatch, native_file_open, operation
    ):
        """Read or reconcile the verified inode after its name is replaced."""
        import atomixos_provision.bundle as bundle_module

        self._mock_appsvc(monkeypatch)
        source = tmp_path / "source"
        source.mkdir()
        payload = source / "payload"
        payload.write_bytes(b"original")
        real_open = bundle_module.os.open
        swapped = False

        def swap_after_pin(path, flags, *args, **kwargs):
            nonlocal swapped
            if str(path).startswith("/proc/self/fd/") and not swapped:
                payload.rename(source / "retained")
                payload.write_bytes(b"replacement")
                payload.chmod(0o600)
                swapped = True
            return real_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(bundle_module.os, "open", swap_after_pin)
        destination = tmp_path / "destination"
        if operation == "snapshot":
            # The swap renames directory entries, so the snapshot is rejected
            # after copying the pinned inode rather than the replacement.
            with pytest.raises(ProvisionError, match="bundle directory changed during snapshot"):
                stage_bundle_files(source, destination)
            assert (destination / "payload").read_bytes() == b"original"
        else:
            grant_managed_file_access(source, writable=True)
            assert (source / "retained").stat().st_mode & 0o777 == 0o640
        assert swapped
        assert payload.stat().st_mode & 0o777 == 0o600

    @pytest.mark.parametrize("operation", ["snapshot", "reconciliation"])
    def test_regular_file_open_requires_non_opening_handles(
        self, tmp_path, monkeypatch, native_file_open, operation
    ):
        """Fail closed on hosts without Linux O_PATH before opening a payload."""
        import atomixos_provision.bundle as bundle_module

        self._mock_appsvc(monkeypatch)
        monkeypatch.delattr(bundle_module.os, "O_PATH", raising=False)
        source = tmp_path / "source"
        source.mkdir()
        (source / "payload").write_bytes(b"data")
        real_open = bundle_module.os.open

        def no_payload_open(path, flags, *args, **kwargs):
            if path == "payload":
                pytest.fail("payload opened without a non-opening handle")
            return real_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(bundle_module.os, "open", no_payload_open)
        with pytest.raises(ProvisionError, match="requires Linux O_PATH"):
            if operation == "snapshot":
                stage_bundle_files(source, tmp_path / "destination")
            else:
                grant_managed_file_access(source)

    def test_copy_bundle_files_enforces_snapshot_limits(self, tmp_path, monkeypatch):
        """Enforce configured total-byte limits during production copies."""
        import atomixos_provision.bundle as bundle_module

        self._mock_appsvc(monkeypatch)
        monkeypatch.setattr(bundle_module, "MAX_BUNDLE_MEMBERS", 100)
        monkeypatch.setattr(bundle_module, "MAX_BUNDLE_MEMBER_BYTES", 100)
        monkeypatch.setattr(bundle_module, "MAX_DECOMPRESSED_BYTES", 5)
        source = tmp_path / "source-files"
        source.mkdir()
        (source / "first.txt").write_bytes(b"abc")
        (source / "second.txt").write_bytes(b"def")

        with pytest.raises(ProvisionError, match="exceeds 5 byte decompressed limit"):
            copy_bundle_files(source, tmp_path / "config")

    def test_rejects_symlinked_files_root_during_reconciliation(self, tmp_path, monkeypatch):
        """Verify that reconciliation never follows a files-root symlink."""
        self._mock_appsvc(monkeypatch)
        target = tmp_path / "target"
        target.mkdir()
        files_root = tmp_path / "files"
        files_root.symlink_to(target, target_is_directory=True)

        with pytest.raises(ProvisionError, match="managed files root must be a directory"):
            grant_managed_file_access(files_root)

    def test_rejects_symlink_source_entries(self, tmp_path, monkeypatch):
        self._mock_appsvc(monkeypatch)
        source = tmp_path / "source_files"
        source.mkdir()
        (tmp_path / "secret.txt").write_text("SECRET")
        (source / "linked-secret.txt").symlink_to(tmp_path / "secret.txt")
        config_root = tmp_path / "config"
        config_root.mkdir()

        with pytest.raises(ProvisionError, match="must not be a symlink"):
            copy_bundle_files(source, config_root)

    def test_rejects_symlink_source_directories(self, tmp_path, monkeypatch):
        self._mock_appsvc(monkeypatch)
        source = tmp_path / "source_files"
        real_dir = tmp_path / "real-dir"
        source.mkdir()
        real_dir.mkdir()
        (source / "linked-dir").symlink_to(real_dir, target_is_directory=True)
        config_root = tmp_path / "config"
        config_root.mkdir()

        with pytest.raises(ProvisionError, match="must not be a symlink"):
            copy_bundle_files(source, config_root)

    def test_creates_empty_files_dir(self, tmp_path, monkeypatch):
        """Verify that creates empty files dir."""
        self._mock_appsvc(monkeypatch)
        source = tmp_path / "source_files"
        source.mkdir()
        config_root = tmp_path / "config"
        config_root.mkdir()

        copy_bundle_files(source, config_root)

        assert (config_root / "files").is_dir()
        assert (config_root / "files").stat().st_mode & 0o777 == 0o550

    def test_none_source(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        copy_bundle_files(None, config_root)
        assert not (config_root / "files").exists()

    def test_stage_bundle_files_accepts_missing_optional_source(self, tmp_path):
        destination = tmp_path / "staged-files"
        destination.mkdir()
        (destination / "old.txt").write_text("old\n")

        stage_bundle_files(tmp_path / "missing-files", destination)

        assert not destination.exists()

    def test_cleans_existing(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        files_dir = config_root / "files"
        files_dir.mkdir()
        (files_dir / "old.txt").write_text("old")

        copy_bundle_files(None, config_root)
        assert not files_dir.exists()


class TestExportBundle:
    """Tests for ``export_bundle_bytes``."""

    @staticmethod
    def _members(bundle: bytes) -> dict[str, bytes | None]:
        """Map each member of a gzip tar bundle to its bytes, or ``None`` for a directory."""
        tar_bytes = gzip.decompress(bundle)
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as archive:
            members = {}
            for member in archive.getmembers():
                extracted = archive.extractfile(member)
                members[member.name] = extracted.read() if extracted is not None else None
            return members

    def test_is_deterministic_and_allowlisted(self, tmp_path):
        """Repeated exports are byte-identical and contain only config.toml and files/."""
        (tmp_path / "config.toml").write_bytes(b"version = 1\n")
        files = tmp_path / "files"
        (files / "nested").mkdir(parents=True)
        (files / "empty").mkdir()
        (files / "z.txt").write_text("z\n")
        (files / "nested" / "a.txt").write_text("a\n")
        for excluded in (
            ".first-config",
            "admin-signers",
            ".atomixos-apply-receipt.json",
            "users.json",
            "quadlet-runtime.json",
        ):
            (tmp_path / excluded).write_text("must not export\n")

        first = export_bundle_bytes(tmp_path)
        second = export_bundle_bytes(tmp_path)

        assert first == second
        assert first.startswith(b"\x1f\x8b")
        assert self._members(first) == {
            "config.toml": b"version = 1\n",
            "files/empty": None,
            "files/nested/a.txt": b"a\n",
            "files/z.txt": b"z\n",
        }

    def test_omits_missing_files_and_preserves_empty_files_directory(self, tmp_path):
        """A missing files/ is omitted, and an empty files/ is exported as a directory."""
        (tmp_path / "config.toml").write_bytes(b"version = 1\n")

        assert set(self._members(export_bundle_bytes(tmp_path))) == {"config.toml"}

        (tmp_path / "files").mkdir()
        assert set(self._members(export_bundle_bytes(tmp_path))) == {"config.toml", "files"}

    def test_round_trips_through_bundle_importer(self, tmp_path):
        """An exported bundle imports back to the same config and managed files."""
        (tmp_path / "config.toml").write_bytes(b"version = 1\n")
        (tmp_path / "files").mkdir()
        (tmp_path / "files" / "cert.pem").write_text("CERT\n")

        bundle = export_bundle_bytes(tmp_path)
        tmpdir, config_path, files_path = prepare_source_bytes(bundle, "config-bundle.tar.gz")
        try:
            assert config_path.read_bytes() == b"version = 1\n"
            assert files_path is not None
            imported_files = tmp_path / "imported-files"
            stage_bundle_files(files_path, imported_files)
            assert (imported_files / "cert.pem").read_text() == "CERT\n"
        finally:
            tmpdir.cleanup()

    def test_exports_imported_tree_with_implicit_parents_at_member_limit(
        self, tmp_path, monkeypatch
    ):
        """Export any tree the importer accepted, even when parents were implicit."""
        monkeypatch.setattr("atomixos_provision.bundle.MAX_BUNDLE_MEMBERS", 4)
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            for name, content in (
                ("config.toml", b"version = 1\n"),
                ("files/d0/x.txt", b"0\n"),
                ("files/d1/x.txt", b"1\n"),
            ):
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))

        def import_tree(source: bytes, config_root: Path) -> None:
            """Import a bundle into a config root through the staging limits."""
            tmpdir, config_path, files_path = prepare_source_bytes(source, "config.tar.gz")
            try:
                config_root.mkdir()
                (config_root / "config.toml").write_bytes(config_path.read_bytes())
                assert files_path is not None
                stage_bundle_files(files_path, config_root / "files")
            finally:
                tmpdir.cleanup()

        # Two implicit parents plus two files fill the four-entry tree budget.
        import_tree(output.getvalue(), tmp_path / "first")
        exported = export_bundle_bytes(tmp_path / "first")
        assert set(self._members(exported)) == {
            "config.toml",
            "files/d0/x.txt",
            "files/d1/x.txt",
        }
        import_tree(exported, tmp_path / "second")
        assert (tmp_path / "second" / "files" / "d1" / "x.txt").read_bytes() == b"1\n"

    def test_rejects_symlinked_export_paths(self, tmp_path):
        """A symlinked config.toml or files/ entry is rejected."""
        target = tmp_path / "target"
        target.write_text("version = 1\n")
        (tmp_path / "config.toml").symlink_to(target)
        with pytest.raises(ProvisionError, match="must be a regular file"):
            export_bundle_bytes(tmp_path)

        (tmp_path / "config.toml").unlink()
        (tmp_path / "config.toml").write_text("version = 1\n")
        (tmp_path / "files").mkdir()
        (tmp_path / "files" / "linked").symlink_to(target)
        with pytest.raises(ProvisionError, match="must not be a symlink"):
            export_bundle_bytes(tmp_path)

    def test_rejects_export_member_over_size_limit(self, tmp_path, monkeypatch):
        """A managed file over the per-member byte limit is rejected."""
        (tmp_path / "config.toml").write_bytes(b"version = 1\n")
        (tmp_path / "files").mkdir()
        (tmp_path / "files" / "large.txt").write_text("large\n")
        monkeypatch.setattr("atomixos_provision.bundle.MAX_BUNDLE_MEMBER_BYTES", 1)

        with pytest.raises(ProvisionError, match=r"exceeds .* byte limit"):
            export_bundle_bytes(tmp_path)

    def test_rejects_export_archive_limits(self, tmp_path, monkeypatch):
        """Exports over the member-count, decompressed, or compressed limit are rejected."""
        (tmp_path / "config.toml").write_bytes(b"version = 1\n")

        monkeypatch.setattr("atomixos_provision.bundle.MAX_BUNDLE_MEMBERS", 0)
        with pytest.raises(ProvisionError, match="member limit"):
            export_bundle_bytes(tmp_path)

        monkeypatch.setattr("atomixos_provision.bundle.MAX_BUNDLE_MEMBERS", 4096)
        monkeypatch.setattr("atomixos_provision.bundle.MAX_DECOMPRESSED_BYTES", 1)
        with pytest.raises(ProvisionError, match="decompressed limit"):
            export_bundle_bytes(tmp_path)

        monkeypatch.setattr("atomixos_provision.bundle.MAX_DECOMPRESSED_BYTES", 256 * 1024 * 1024)
        monkeypatch.setattr("atomixos_provision.bundle.MAX_SOURCE_BYTES", 1)
        with pytest.raises(ProvisionError, match="export exceeds"):
            export_bundle_bytes(tmp_path)

    def test_rejects_member_limit_while_snapshotting(self, tmp_path, monkeypatch):
        """Snapshotting rejects too many members before copying any file."""
        import atomixos_provision.bundle as bundle_module

        (tmp_path / "config.toml").write_bytes(b"version = 1\n")
        (tmp_path / "files").mkdir()
        (tmp_path / "files" / "a.txt").write_text("a\n")
        (tmp_path / "files" / "b.txt").write_text("b\n")
        copied_members = 0
        source_inodes = {(tmp_path / "files" / name).stat().st_ino for name in ("a.txt", "b.txt")}
        fdopen = bundle_module.os.fdopen

        def counting_fdopen(fd, *args, **kwargs):
            """Count snapshot files opened before the member limit is rejected."""
            nonlocal copied_members
            if bundle_module.os.fstat(fd).st_ino in source_inodes:
                copied_members += 1
            return fdopen(fd, *args, **kwargs)

        monkeypatch.setattr(bundle_module, "MAX_BUNDLE_MEMBERS", 1)
        monkeypatch.setattr(bundle_module.os, "fdopen", counting_fdopen)

        with pytest.raises(ProvisionError, match="member limit"):
            export_bundle_bytes(tmp_path)

        # Enumeration reserves every discovered name before copying any file.
        assert copied_members == 0


@pytest.mark.parametrize("member", ["config.toml", "files/private.txt"])
def test_export_rejects_hard_links(tmp_path, member):
    """A privileged snapshot must not export unrelated state through hard links."""
    (tmp_path / "config.toml").write_text("version = 1\n")
    (tmp_path / "files").mkdir()
    secret = tmp_path / "admin-signers"
    secret.write_text("not part of the export\n")
    target = tmp_path / member
    target.unlink(missing_ok=True)
    target.hardlink_to(secret)
    with pytest.raises(ProvisionError, match="single-link"):
        export_bundle_bytes(tmp_path)


@pytest.mark.parametrize("member", ["config.toml", "files/private.txt"])
@pytest.mark.parametrize("replacement", ["regular", "fifo"])
def test_export_rejects_inode_substitution(tmp_path, monkeypatch, member, replacement):
    """A file replaced between inspection and open is rejected without FIFO blocking."""
    import os

    import atomixos_provision.bundle as bundle_module

    (tmp_path / "config.toml").write_text("version = 1\n")
    (tmp_path / "files").mkdir()
    target = tmp_path / member
    if not target.exists():
        target.write_text("original\n")
    other = tmp_path / "replacement"
    if replacement == "regular":
        other.write_text("substituted\n")
    else:
        os.mkfifo(other)
    open_file = os.open
    swapped = False

    def swap_before_open(path, flags, *args, **kwargs):
        """Replace the target with the substitute just before its first open."""
        nonlocal swapped
        if not swapped and (path == target or (path == target.name and "dir_fd" in kwargs)):
            swapped = True
            os.replace(other, target)
            # Linux first pins the name with a non-opening O_PATH handle; other
            # hosts open it directly and must not block on a substituted FIFO.
            assert flags & (getattr(os, "O_PATH", 0) | os.O_NONBLOCK)
        return open_file(path, flags, *args, **kwargs)

    monkeypatch.setattr(bundle_module.os, "open", swap_before_open)
    with pytest.raises(ProvisionError, match=r"changed during snapshot|single-link regular"):
        export_bundle_bytes(tmp_path)
    assert swapped


class TestPrepareSourcePath:
    def test_toml_file(self, tmp_path):
        config = tmp_path / "config.toml"
        config.write_text("version = 1")
        tmpdir, config_path, files_path = prepare_source_path(config)
        assert tmpdir is None
        assert config_path == config
        assert files_path is None

    def test_unsupported_file(self, tmp_path):
        bad = tmp_path / "config.txt"
        bad.write_text("not a bundle")
        with pytest.raises(ProvisionError, match="supported import inputs"):
            prepare_source_path(bad)


class TestPrepareSourceBytes:
    def test_plain_toml(self):
        tmpdir, config_path, files_path = prepare_source_bytes(b"version = 1", "config.toml")
        assert config_path.read_text() == "version = 1"
        assert files_path is None
        tmpdir.cleanup()
