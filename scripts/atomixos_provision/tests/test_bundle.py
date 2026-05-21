"""Tests for atomixos_provision.bundle module."""

import gzip
import io
import tarfile

import pytest

from atomixos_provision.bundle import (
    copy_bundle_files,
    detect_bundle_kind,
    extract_bundle_archive,
    prepare_source_bytes,
    prepare_source_path,
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
    def _mock_appsvc(self, monkeypatch):
        chowns: list[tuple[str, int, int]] = []
        monkeypatch.setattr(
            "atomixos_provision.bundle.pwd.getpwnam",
            lambda _name: type("Pw", (), {"pw_uid": 1000, "pw_gid": 1000})(),
        )
        monkeypatch.setattr(
            "atomixos_provision.bundle.os.chown",
            lambda path, uid, gid: chowns.append((str(path), uid, gid)),
        )
        return chowns

    def test_copies_files(self, tmp_path, monkeypatch):
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
        assert (config_root / "files" / "cert.pem").stat().st_mode & 0o777 == 0o600
        assert (config_root / "files" / "subdir" / "key.pem").stat().st_mode & 0o777 == 0o600
        assert (str(config_root / "files" / "cert.pem"), 1000, 1000) in chowns
        assert (str(config_root / "files" / "subdir" / "key.pem"), 1000, 1000) in chowns

    def test_creates_empty_files_dir(self, tmp_path, monkeypatch):
        self._mock_appsvc(monkeypatch)
        source = tmp_path / "source_files"
        source.mkdir()
        config_root = tmp_path / "config"
        config_root.mkdir()

        copy_bundle_files(source, config_root)

        assert (config_root / "files").is_dir()
        assert (config_root / "files").stat().st_mode & 0o777 == 0o700

    def test_none_source(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        copy_bundle_files(None, config_root)
        assert not (config_root / "files").exists()

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
        tmpdir, config_path, files_path = prepare_source_bytes(
            b"version = 1", "config.toml"
        )
        assert config_path.read_text() == "version = 1"
        assert files_path is None
        tmpdir.cleanup()
