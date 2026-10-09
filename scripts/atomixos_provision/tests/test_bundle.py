"""Tests for atomixos_provision.bundle module."""

import gzip
import io
import tarfile

import pytest

from atomixos_provision.bundle import (
    copy_bundle_files,
    detect_bundle_kind,
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

    def test_copies_files(self, tmp_path, monkeypatch):
        """Verify that copies files."""
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
        assert (
            sum(path.startswith("fd:") for path, uid, gid in chowns if (uid, gid) == (1000, 2000))
            == 3
        )

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
