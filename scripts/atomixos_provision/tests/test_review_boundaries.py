"""Regression coverage for PR review privilege and resource boundaries."""

import hashlib
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from atomixos_provision import bundle, provision, server, staging
from atomixos_provision.apply_transaction import ApplyRecovery
from atomixos_provision.config import ProvisionError
from atomixos_provision.state import is_provisioned_config_root


@pytest.mark.parametrize("name", [".first-config", "config.toml"])
def test_state_rejects_symlink_marker(tmp_path, name):
    """A symlink to a valid file must not mark the device provisioned."""
    target = tmp_path / "target"
    target.write_text("version = 1\n")
    (tmp_path / name).symlink_to(target)
    assert not is_provisioned_config_root(tmp_path)


def test_request_limit_precedes_hashing(tmp_path, monkeypatch):
    """The privileged verifier rejects oversized evidence before reading it."""
    payload = b"oversized"
    (tmp_path / "request.bin").write_bytes(payload)
    monkeypatch.setattr(bundle, "MAX_SOURCE_BYTES", len(payload) - 1)

    def unexpected_hash(_path):
        pytest.fail("oversized request must not be hashed")

    monkeypatch.setattr(staging, "sha256_file", unexpected_hash)
    with pytest.raises(ProvisionError, match=r"exceeds .* byte limit"):
        staging._verify_staged_request(
            tmp_path,
            {"size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()},
            os.getuid(),
            os.getgid(),
        )


def test_request_hash_is_bounded_when_evidence_grows(tmp_path, monkeypatch):
    """Growth after metadata validation must not turn hashing into an unbounded read."""
    payload = tmp_path / "request.bin"
    payload.write_bytes(b"x")
    original_fdopen = os.fdopen

    def growing_fdopen(fd, *args, **kwargs):
        payload.write_bytes(b"x" * 100)
        return original_fdopen(fd, *args, **kwargs)

    monkeypatch.setattr(staging.os, "fdopen", growing_fdopen)
    with pytest.raises(ProvisionError, match=r"exceeds 8 byte limit"):
        staging.sha256_file(payload, max_bytes=8)


@pytest.mark.parametrize("transport", ["network", "fleet"])
def test_cli_reconciles_discarded_initial_recovery(tmp_path, monkeypatch, transport):
    """CLI recovery uses the same transport-aware reconciliation as the worker."""
    monkeypatch.setenv("ATOMIXOS_BOOTSTRAP_TRANSPORT", transport)
    monkeypatch.setattr(
        provision, "recover_interrupted_apply", lambda _root: ApplyRecovery(None, True)
    )
    calls = []
    monkeypatch.setattr(provision.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    result = CliRunner().invoke(server.cli, ["recover", str(tmp_path / "config")])
    assert result.exit_code == 0, result.exception
    assert bool(calls) == (transport == "network")


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


def test_recovery_unit_receives_bootstrap_transport():
    """The recovery service must not default fleet devices to network recovery."""
    module = Path(__file__).resolve().parents[3] / "modules" / "first-boot.nix"
    recovery_unit = module.read_text().split("systemd.services.atomixos-config-recover = {")[1]
    recovery_unit = recovery_unit.split("serviceConfig = {")[0]
    assert "environment.ATOMIXOS_BOOTSTRAP_TRANSPORT = bootstrapTransport;" in recovery_unit
