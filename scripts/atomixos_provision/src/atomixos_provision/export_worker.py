"""UUID-correlated, fixed-purpose privileged bundle exports."""

import asyncio
import contextlib
import fcntl
import logging
import os
import re
import shutil
import stat
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from atomixos_provision.bundle import MAX_SOURCE_BYTES
from atomixos_provision.exceptions import ApiError, ConflictError

CONFIG_ROOT = Path("/data/config")
RUNTIME_ROOT = Path("/run/atomixos-provision/export")
MAX_EXPORTS = 4
WAIT_SECONDS = 130
RETENTION_SECONDS = 300
UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
REQUEST_NAME = re.compile(rf"({UUID_PATTERN})\.(request|ack)")
logger = logging.getLogger(__name__)


class ExportTimeout(ApiError):
    """The privileged export worker published no result within ``WAIT_SECONDS`` (HTTP 504)."""

    status_code = 504


@contextlib.contextmanager
def _lock(path: Path):
    """Hold an exclusive ``flock`` on a pre-created control file for the block.

    The file is opened without following a final symlink, without creating it, and
    without blocking on a FIFO; only acquiring the lock itself waits. Raise
    ``ApiError`` if the path is not a regular file and ``OSError`` if it is missing
    or a symlink.
    """
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ApiError("Invalid export lock file")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _publish(path: Path, content: bytes) -> None:
    """Atomically replace ``path`` with ``content`` as a mode ``0640`` file.

    Write a ``.export-*`` temporary file beside ``path`` and rename it into place,
    so readers see either no result or the complete one. The setgid results
    directory supplies the API group. The temporary file is removed on failure,
    and the finalizer removes any left by a killed worker.
    """
    fd, temporary = tempfile.mkstemp(prefix=".export-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content)
            output.flush()
            os.fchmod(output.fileno(), 0o640)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _marker(path: Path) -> None:
    """Create an empty marker file, raising ``FileExistsError`` if the path exists.

    Exclusive creation never replaces or follows an existing entry.
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640)
    os.close(fd)


def _read_result(path: Path, limit: int) -> bytes | None:
    """Return a published result's bytes, or ``None`` if it does not exist yet.

    Open without following symlinks or blocking on a FIFO. Raise ``ApiError`` if
    the entry is not a single-link regular file or holds more than ``limit`` bytes.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ApiError("Invalid export result")
        payload = source.read(limit + 1)
    if len(payload) > limit:
        raise ApiError("Export result exceeds its size limit")
    return payload


def _submit(root: Path, request_id: str) -> None:
    """Admit ``request_id`` by publishing ``requests/<uuid>.request`` under the queue lock.

    Every UUID with a pending request or acknowledgement, an active claim, or a
    retained result holds one slot, counted once however many of those entries it
    has. Raise ``ConflictError`` when ``MAX_EXPORTS`` slots are taken or the UUID
    is already present.
    """
    with _lock(root / "queue.lock"):
        occupied = {
            path.name.split(".", 1)[0]
            for directory in ("requests", "active", "results")
            for path in (root / directory).iterdir()
            if path.name.endswith((".request", ".ack", ".tar.gz", ".error"))
        }
        if len(occupied) >= MAX_EXPORTS:
            raise ConflictError("The export queue is busy; retry shortly")
        if request_id in occupied:
            raise ConflictError("Export request UUID already exists")
        _marker(root / "requests" / f"{request_id}.request")


def _acknowledge(root: Path, request_id: str) -> None:
    """Release ``request_id`` by withdrawing its request and publishing an acknowledgement.

    Under the queue lock, remove the request if the worker has not claimed it yet,
    then publish ``requests/<uuid>.ack``. The acknowledgement keeps the UUID's slot
    until the worker deletes its result, or until cleanup expires it.
    """
    with _lock(root / "queue.lock"):
        (root / "requests" / f"{request_id}.request").unlink(missing_ok=True)
        _marker(root / "requests" / f"{request_id}.ack")


async def request_export(root: Path = RUNTIME_ROOT) -> bytes:
    """Submit an export to the root worker and return this request's archive bytes.

    Admit a fresh UUID, then poll every 100 ms for up to ``WAIT_SECONDS`` for that
    UUID's error or archive, so another export's output is never returned. Once
    the request is admitted, try to acknowledge it on every exit, including on
    cancellation, so the worker withdraws it or deletes its result. A failed
    acknowledgement is logged, not raised.

    Raise ``ConflictError`` when admission fails, ``ApiError`` with the worker's
    message when it publishes an error, ``ExportTimeout`` when no result appears
    in time, and ``ApiError`` when the runtime directory cannot be used.
    """
    request_id = str(uuid4())
    submission = asyncio.create_task(asyncio.to_thread(_submit, root, request_id))
    try:
        await asyncio.shield(submission)
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            error = await asyncio.to_thread(
                _read_result, root / "results" / f"{request_id}.error", 4096
            )
            if error is not None:
                raise ApiError(error.decode("utf-8", errors="replace"))
            archive = await asyncio.to_thread(
                _read_result, root / "results" / f"{request_id}.tar.gz", MAX_SOURCE_BYTES
            )
            if archive is not None:
                return archive
            await asyncio.sleep(0.1)
        raise ExportTimeout("Configuration export timed out; retry or inspect the export service")
    except OSError as exc:
        raise ApiError("Configuration export worker is unavailable") from exc
    finally:
        # Finish admission before acknowledging, even if the HTTP request was
        # cancelled while its submission thread was still running.
        try:
            await asyncio.shield(submission)
        except (ApiError, OSError):
            pass
        else:
            try:
                await asyncio.shield(asyncio.to_thread(_acknowledge, root, request_id))
            except OSError:
                logger.exception("Unable to acknowledge export %s", request_id)


def _discard(path: Path) -> None:
    """Delete a claimed file, symlink, or directory tree without following symlinks."""
    if stat.S_ISDIR(path.lstat().st_mode):
        shutil.rmtree(path)
    else:
        path.unlink()


def _finish_interrupted(root: Path) -> None:
    """Resolve claims and partial output left by a previous worker run.

    For each claimed ``<uuid>.request`` without a published archive, publish a
    failure ``<uuid>.error``. Then delete every entry in ``active/`` and every
    ``.export-*`` temporary file in ``results/``. The caller holds the queue lock.
    """
    for path in (root / "active").iterdir():
        match = REQUEST_NAME.fullmatch(path.name)
        if match and match[2] == "request":
            request_id = match[1]
            if not (root / "results" / f"{request_id}.tar.gz").exists():
                _publish(
                    root / "results" / f"{request_id}.error",
                    b"Configuration export worker stopped before completing the archive",
                )
        _discard(path)
    for path in (root / "results").glob(".export-*"):
        path.unlink()


def _cleanup(root: Path) -> None:
    """Delete results, requests, and acknowledgements older than ``RETENTION_SECONDS``.

    Each expired entry is first renamed into ``active/`` under a random name, so an
    API-writable entry is never inspected in place. The caller holds the queue lock.
    """
    cutoff = time.time() - RETENTION_SECONDS
    for directory in ("results", "requests"):
        for path in (root / directory).iterdir():
            if path.lstat().st_mtime < cutoff:
                # Move API-writable entries into the private claim directory
                # before inspecting/removing them. Never traverse request paths.
                claimed = root / "active" / str(uuid4())
                try:
                    path.rename(claimed)
                except FileNotFoundError:
                    continue
                _discard(claimed)


def drain_exports(
    *,
    finalize: bool = False,
    root: Path = RUNTIME_ROOT,
    config_root: Path = CONFIG_ROOT,
) -> None:
    """Process queued export markers until ``requests/`` is empty.

    Hold the worker lock throughout. Under the queue lock, first resolve claims
    left by an interrupted run and expire abandoned entries. With ``finalize``
    set, as the systemd stop-post finalizer does, stop there.

    Otherwise claim markers in name order by renaming them into ``active/``.
    Discard any marker that is not an empty, single-link regular file named
    ``<uuid>.request`` or ``<uuid>.ack``. An acknowledgement deletes that UUID's
    result. A request whose result already exists is dropped, so a replayed UUID
    never overwrites output. Any other request exports ``config_root`` outside the
    queue lock and publishes ``<uuid>.tar.gz``, or a generic ``<uuid>.error`` if
    exporting or publishing the archive raises. The claim is removed only after a
    result is published. If the error cannot be published either, the exception
    propagates and the claim stays for the finalizer.

    Markers carry no content, and their names are the only input. Only the root CLI
    calls this in production, with the default paths. ``root`` and ``config_root``
    exist only so tests can inject paths; they are not part of the request or CLI
    protocol.
    """
    with _lock(root / "worker.lock"):
        with _lock(root / "queue.lock"):
            _finish_interrupted(root)
            _cleanup(root)
        if finalize:
            return
        while True:
            with _lock(root / "queue.lock"):
                pending = sorted((root / "requests").iterdir())
                if not pending:
                    return
                request = pending[0]
                match = REQUEST_NAME.fullmatch(request.name)
                claimed = root / "active" / (request.name if match else str(uuid4()))
                request.rename(claimed)
                metadata = claimed.lstat()
                valid = (
                    match is not None
                    and stat.S_ISREG(metadata.st_mode)
                    and metadata.st_nlink == 1
                    and metadata.st_size == 0
                )
                if not valid:
                    _discard(claimed)
                    continue
                request_id, operation = match.groups()
                archive = root / "results" / f"{request_id}.tar.gz"
                error = root / "results" / f"{request_id}.error"
                if operation == "ack":
                    archive.unlink(missing_ok=True)
                    error.unlink(missing_ok=True)
                    claimed.unlink()
                    continue
                # Replayed UUIDs never overwrite completed output.
                if archive.exists() or error.exists():
                    claimed.unlink()
                    continue
            try:
                from atomixos_provision.provision import locked_export_config_bytes

                payload = locked_export_config_bytes(config_root)
                _publish(archive, payload)
            except Exception:
                logger.exception("Configuration export %s failed", request_id)
                _publish(error, b"Configuration export failed; inspect the export service logs")
            # Keep the claim when publication fails so the finalizer can record a failure.
            claimed.unlink()
