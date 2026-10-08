"""Tests for UUID export admission, privilege-boundary inputs, and completion."""

import asyncio
import io
import os
import tarfile
import time
from pathlib import Path
from uuid import uuid4

import pytest
from litestar.testing import AsyncTestClient

from atomixos_provision import export_worker as worker
from atomixos_provision.app import create_app
from atomixos_provision.domain.config.service import ConfigService
from atomixos_provision.exceptions import ApiError, ConflictError


@pytest.fixture
def export_root(tmp_path):
    """Provide the layout normally installed by systemd-tmpfiles."""
    root = tmp_path / "export"
    root.mkdir()
    for directory in ("requests", "active", "results"):
        (root / directory).mkdir(mode=0o2750)
    for name in ("queue.lock", "worker.lock"):
        (root / name).touch(mode=0o600)
    return root


@pytest.fixture
def config_root(tmp_path):
    """Provide canonical desired state and a managed payload."""
    root = tmp_path / "config"
    (root / "files").mkdir(parents=True)
    (root / "config.toml").write_text("version = 1\n")
    (root / "files" / "private.txt").write_text("changed payload\n")
    return root


async def wait_for_request(root, count=1):
    """Wait until API tasks have published requests before running the worker."""
    async with asyncio.timeout(3):
        while len(list((root / "requests").glob("*.request"))) < count:
            await asyncio.sleep(0.01)


async def test_complete_export_and_acknowledgement(export_root, config_root):
    """Only a complete archive is returned and acknowledgement removes it."""
    task = asyncio.create_task(worker.request_export(export_root))
    await wait_for_request(export_root)
    await asyncio.to_thread(worker.drain_exports, root=export_root, config_root=config_root)
    payload = await task
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        assert archive.getnames() == ["config.toml", "files", "files/private.txt"]
        assert archive.extractfile("files/private.txt").read() == b"changed payload\n"
    await asyncio.to_thread(worker.drain_exports, root=export_root, config_root=config_root)
    assert not list((export_root / "results").iterdir())
    assert not list((export_root / "active").iterdir())
    assert not list((export_root / "requests").iterdir())


async def test_concurrent_exports_are_uuid_correlated(export_root, config_root, monkeypatch):
    """Different requests cannot receive each other's or an old request's result."""
    ids = [uuid4(), uuid4()]
    expected = iter(ids)
    monkeypatch.setattr(worker, "uuid4", lambda: next(expected))
    tasks = [asyncio.create_task(worker.request_export(export_root)) for _ in ids]
    await wait_for_request(export_root, 2)
    (export_root / "results" / f"{uuid4()}.tar.gz").write_bytes(b"old archive")
    for request_id, content in zip(ids, (b"first archive", b"second archive"), strict=True):
        worker._publish(export_root / "results" / f"{request_id}.tar.gz", content)
    assert await asyncio.gather(*tasks) == [b"first archive", b"second archive"]


async def test_worker_failure_is_explicit(export_root, config_root, monkeypatch):
    """A failed export produces an error, not an archive or an endless wait."""

    def fail(_root):
        raise PermissionError("unreadable managed file")

    monkeypatch.setattr("atomixos_provision.provision.locked_export_config_bytes", fail)
    task = asyncio.create_task(worker.request_export(export_root))
    await wait_for_request(export_root)
    await asyncio.to_thread(worker.drain_exports, root=export_root, config_root=config_root)
    with pytest.raises(ApiError, match="export failed"):
        await task
    assert not list((export_root / "results").glob("*.tar.gz"))


async def test_timeout_cancels_unclaimed_request(export_root, monkeypatch):
    """A missing worker cannot hold an HTTP request indefinitely."""
    monkeypatch.setattr(worker, "WAIT_SECONDS", 0.02)
    with pytest.raises(worker.ExportTimeout):
        await worker.request_export(export_root)
    assert not list((export_root / "requests").glob("*.request"))
    assert len(list((export_root / "requests").glob("*.ack"))) == 1


async def test_cancelled_request_is_acknowledged(export_root):
    """Cancellation leaves a cleanup marker rather than an unbounded export slot."""
    task = asyncio.create_task(worker.request_export(export_root))
    await wait_for_request(export_root)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not list((export_root / "requests").glob("*.request"))
    assert len(list((export_root / "requests").glob("*.ack"))) == 1


async def test_busy_queue_does_not_publish_extra_markers(export_root):
    """Admission accounts for both pending work and retained results."""
    for _ in range(worker.MAX_EXPORTS - 1):
        worker._submit(export_root, str(uuid4()))
    (export_root / "results" / f"{uuid4()}.tar.gz").write_bytes(b"retained")
    with pytest.raises(ConflictError, match="export queue"):
        await worker.request_export(export_root)
    assert not list((export_root / "requests").glob("*.ack"))
    assert len(list((export_root / "requests").glob("*.request"))) == worker.MAX_EXPORTS - 1


def test_finalize_interrupted_claims_and_partial_output(export_root):
    """A killed worker publishes failure while preserving a completed archive."""
    failed, complete = str(uuid4()), str(uuid4())
    for request_id in (failed, complete):
        (export_root / "active" / f"{request_id}.request").touch()
    (export_root / "results" / f"{complete}.tar.gz").write_bytes(b"complete")
    (export_root / "results" / ".export-partial").write_bytes(b"partial")
    worker.drain_exports(root=export_root, finalize=True)
    assert (export_root / "results" / f"{failed}.error").is_file()
    assert not (export_root / "results" / f"{complete}.error").exists()
    assert (export_root / "results" / f"{complete}.tar.gz").read_bytes() == b"complete"
    assert not list((export_root / "results").glob(".export-*"))
    assert not list((export_root / "active").iterdir())


def test_expire_abandoned_requests_and_results(export_root):
    """Periodic cleanup frees expired slots, including abandoned error results."""
    old = time.time() - worker.RETENTION_SECONDS - 1
    stale = [
        export_root / "requests" / f"{uuid4()}.request",
        export_root / "results" / f"{uuid4()}.tar.gz",
        export_root / "results" / f"{uuid4()}.error",
    ]
    for path in stale:
        path.write_bytes(b"")
        os.utime(path, (old, old))
    fresh = export_root / "results" / f"{uuid4()}.tar.gz"
    fresh.write_bytes(b"fresh")
    worker.drain_exports(root=export_root, finalize=True)
    assert all(not path.exists() for path in stale)
    assert fresh.read_bytes() == b"fresh"


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "directory", "content", "name"])
def test_reject_untrusted_request_entries(export_root, config_root, monkeypatch, kind):
    """Request data never becomes a path, command, or privileged read target."""
    target = config_root / "config.toml"
    original = target.read_bytes()
    path = export_root / "requests" / f"{uuid4()}.request"
    if kind == "symlink":
        path.symlink_to(target)
    elif kind == "hardlink":
        path.hardlink_to(target)
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind == "directory":
        path.mkdir()
        (path / "escape").symlink_to(config_root)
    elif kind == "content":
        path.write_text("/etc/shadow\n")
    else:
        path = path.with_name("not-a-uuid.request")
        path.touch()

    def unexpected(_root):
        pytest.fail("invalid marker must not trigger an export")

    monkeypatch.setattr("atomixos_provision.provision.locked_export_config_bytes", unexpected)
    worker.drain_exports(root=export_root, config_root=config_root)
    assert target.read_bytes() == original
    assert not list((export_root / "requests").iterdir())
    assert not list((export_root / "results").iterdir())


def test_duplicate_request_never_overwrites_result(export_root, config_root):
    """Replayed UUIDs retain their original terminal result."""
    request_id = str(uuid4())
    result = export_root / "results" / f"{request_id}.tar.gz"
    result.write_bytes(b"previous")
    (export_root / "requests" / f"{request_id}.request").touch()
    worker.drain_exports(root=export_root, config_root=config_root)
    assert result.read_bytes() == b"previous"


def test_worker_drains_requests_arriving_during_export(export_root, config_root, monkeypatch):
    """A path activation drains newly queued work before exiting."""
    first, second = str(uuid4()), str(uuid4())
    worker._submit(export_root, first)
    exports = 0

    def export(_root):
        nonlocal exports
        exports += 1
        if exports == 1:
            worker._submit(export_root, second)
        return b"archive"

    monkeypatch.setattr("atomixos_provision.provision.locked_export_config_bytes", export)
    worker.drain_exports(root=export_root, config_root=config_root)
    assert exports == 2
    assert (export_root / "results" / f"{first}.tar.gz").read_bytes() == b"archive"
    assert (export_root / "results" / f"{second}.tar.gz").read_bytes() == b"archive"


def test_atomic_output_is_group_readable(export_root, monkeypatch):
    """No final result exists until the entire restrictive output is published."""
    result = export_root / "results" / f"{uuid4()}.tar.gz"
    replace = os.replace

    def inspect(source, destination):
        assert not result.exists()
        assert os.stat(source).st_mode & 0o777 == 0o640
        assert Path(source).read_bytes() == b"complete"
        replace(source, destination)

    monkeypatch.setattr(worker.os, "replace", inspect)
    worker._publish(result, b"complete")
    assert result.read_bytes() == b"complete"


async def test_production_service_delegates_to_worker(monkeypatch):
    """Production never tries to read private managed files as the API user."""

    async def export():
        return b"privileged archive"

    monkeypatch.setattr(worker, "request_export", export)
    assert await ConfigService(worker.CONFIG_ROOT).export_config() == b"privileged archive"


@pytest.mark.parametrize(
    "error, status",
    [
        (ApiError("Export failed"), 500),
        (worker.ExportTimeout("Timed out"), 504),
        (ConflictError("Queue full"), 409),
    ],
)
async def test_export_http_errors_are_json(config_root, monkeypatch, error, status):
    """Authenticated export failures return explicit JSON, never gzip headers."""

    class NonceStore:
        async def consume(self, _nonce):
            return True

    async def fail(_self):
        raise error

    (config_root / "admin-signers").write_text("ssh-ed25519 AAAA test\n")
    monkeypatch.setattr("atomixos_provision.auth.verify_ssh_signature", lambda *_args: True)
    monkeypatch.setattr(ConfigService, "export_config", fail)
    app = create_app(config_root=config_root, nonce_store=NonceStore())
    async with AsyncTestClient(app=app) as client:
        response = await client.get(
            "/api/config/export",
            headers={"x-atomixos-nonce": "test", "x-atomixos-signature": "dGVzdA=="},
        )
    assert response.status_code == status
    assert response.json() == {"error": str(error)}
    assert response.headers["content-type"].startswith("application/json")
    assert "content-disposition" not in response.headers
