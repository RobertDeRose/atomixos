"""Runtime staging contract for unprivileged provisioning jobs."""

from __future__ import annotations

import contextlib
import errno
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atomixos_provision.config import ProvisionError

MANIFEST_VERSION = 1
RESULT_VERSION = 1
JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
DEFAULT_RUNTIME_ROOT = Path("/run/atomixos-provision")
MAX_CONTROL_JSON_BYTES = 1024 * 1024
STAGED_RESERVATION_TTL_SECONDS = 300
RUNTIME_ROOT_MODE = 0o755
QUEUE_DIR_MODE = 0o2770
RESULTS_DIR_MODE = 0o2750
ACTIVE_DIR_MODE = 0o2750


@dataclass(frozen=True)
class RuntimePaths:
    root: Path

    @property
    def queue(self) -> Path:
        return self.root / "queue"

    @property
    def active(self) -> Path:
        return self.root / "active"

    @property
    def results(self) -> Path:
        return self.root / "results"

    @property
    def queue_lock(self) -> Path:
        return self.root / "queue.lock"

    @property
    def queue_sequence(self) -> Path:
        return self.queue / ".sequence"


@dataclass(frozen=True)
class ClaimedJob:
    job_id: str
    path: Path


def runtime_paths(root: Path) -> RuntimePaths:
    return RuntimePaths(root.resolve(strict=False))


def ensure_runtime_layout(paths: RuntimePaths, *, for_worker: bool = False) -> None:
    _ensure_directory(paths.root, RUNTIME_ROOT_MODE)
    _ensure_directory(paths.queue, QUEUE_DIR_MODE)
    if for_worker or paths.results.exists():
        _ensure_directory(paths.results, RESULTS_DIR_MODE)
    if for_worker:
        _ensure_directory(paths.active, ACTIVE_DIR_MODE)


def _ensure_directory(path: Path, mode: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(mode)
    except PermissionError:
        return


CONTROL_FILE_SUFFIXES = (".ready", ".reserve")


def validate_job_id(job_id: str) -> str:
    if not isinstance(job_id, str) or not JOB_ID_RE.match(job_id):
        raise ProvisionError(f"invalid staged job id: {job_id!r}")
    if "/" in job_id or job_id in {".", ".."}:
        raise ProvisionError(f"invalid staged job id: {job_id!r}")
    if job_id.endswith(CONTROL_FILE_SUFFIXES):
        raise ProvisionError(f"staged job id uses reserved suffix: {job_id!r}")
    return job_id


def validate_relative_path(raw_path: str) -> str:
    if not isinstance(raw_path, str) or raw_path == "":
        raise ProvisionError("staged manifest path must be a non-empty string")
    path = Path(raw_path)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ProvisionError(f"unsafe staged manifest path: {raw_path!r}")
    normalized = path.as_posix()
    if normalized != raw_path.replace(os.sep, "/"):
        raise ProvisionError(f"non-normalized staged manifest path: {raw_path!r}")
    return normalized


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def tree_manifest(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    entries: list[dict[str, Any]] = []
    for current in sorted(root.rglob("*")):
        try:
            current_stat = current.lstat()
        except OSError as exc:
            raise ProvisionError(f"cannot stat staged path: {current}") from exc
        if stat.S_ISLNK(current_stat.st_mode):
            raise ProvisionError(f"staged path must not be a symlink: {current}")
        rel = current.relative_to(root).as_posix()
        mode = stat.S_IMODE(current_stat.st_mode)
        if stat.S_ISDIR(current_stat.st_mode):
            entries.append({"path": rel, "type": "dir", "mode": mode})
        elif stat.S_ISREG(current_stat.st_mode):
            entries.append(
                {
                    "path": rel,
                    "type": "file",
                    "mode": mode,
                    "size": current_stat.st_size,
                    "sha256": sha256_file(current),
                }
            )
        else:
            raise ProvisionError(f"staged path must be a regular file or directory: {current}")
    return entries


def write_json_atomic(
    path: Path,
    payload: dict[str, Any],
    *,
    mode: int = 0o640,
    owner: tuple[int, int] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as output:
        tmp_path = Path(output.name)
        json.dump(payload, output, sort_keys=True, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    try:
        if owner is not None:
            os.chown(tmp_path, owner[0], owner[1])
        tmp_path.chmod(mode)
        os.replace(tmp_path, path)
        fsync_directory(path.parent)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(read_control_file(path).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProvisionError(f"invalid staged JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ProvisionError(f"staged JSON must be an object: {path}")
    return payload


def read_control_file(path: Path, *, max_bytes: int = MAX_CONTROL_JSON_BYTES) -> bytes:
    """Read a small staged control file without following symlinks."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ProvisionError(f"staged control file must not be a symlink: {path}") from exc
        raise
    try:
        path_stat = os.fstat(fd)
        if not stat.S_ISREG(path_stat.st_mode):
            raise ProvisionError(f"staged control file must be a regular file: {path}")
        if path_stat.st_size > max_bytes:
            raise ProvisionError(f"staged control file is too large: {path}")
        return os.read(fd, max_bytes + 1)
    finally:
        os.close(fd)


def publish_ready_marker(paths: RuntimePaths, job_id: str) -> Path:
    validate_job_id(job_id)
    ready_path = paths.queue / f"{job_id}.ready"
    tmp_path = paths.queue / f".{job_id}.ready.{os.getpid()}"
    with queue_operation_lock(paths):
        reserve_path = paths.queue / f"{job_id}.reserve"
        try:
            sequence, created_at = _reservation_sort_key(reserve_path)
        except (FileNotFoundError, ProvisionError):
            sequence = _next_ready_sequence_locked(paths)
            created_at = time.time()
        tmp_path.write_text(
            json.dumps({"job_id": job_id, "sequence": sequence, "created_at": created_at})
            + "\n",
            encoding="utf-8",
        )
        tmp_path.chmod(0o640)
        os.replace(tmp_path, ready_path)
        reserve_path.unlink(missing_ok=True)
        fsync_directory(paths.queue)
    return ready_path


def reserve_staged_job_slot(paths: RuntimePaths, job_id: str, max_jobs: int) -> bool:
    """Reserve bounded FIFO capacity before an accepted job is published."""
    validate_job_id(job_id)
    ensure_runtime_layout(paths)
    reserve_path = paths.queue / f"{job_id}.reserve"
    with queue_operation_lock(paths):
        _cleanup_stale_reservations_locked(paths)
        if _count_staged_jobs_locked(paths) >= max_jobs:
            return False
        sequence = _next_ready_sequence_locked(paths)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(reserve_path, flags, 0o640)
        except FileExistsError as exc:
            raise ProvisionError(f"staged job reservation already exists: {job_id}") from exc
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(
                    {"job_id": job_id, "sequence": sequence, "created_at": time.time()},
                    output,
                )
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
        except Exception:
            reserve_path.unlink(missing_ok=True)
            raise
        fsync_directory(paths.queue)
        return True


def release_staged_job_slot(paths: RuntimePaths, job_id: str) -> None:
    """Release a pre-publication capacity reservation."""
    validate_job_id(job_id)
    with queue_operation_lock(paths):
        (paths.queue / f"{job_id}.reserve").unlink(missing_ok=True)
        fsync_directory(paths.queue)


def refresh_staged_job_slot(paths: RuntimePaths, job_id: str) -> None:
    """Refresh an in-progress pre-publication capacity reservation."""
    validate_job_id(job_id)
    with queue_operation_lock(paths):
        reserve_path = paths.queue / f"{job_id}.reserve"
        if reserve_path.exists():
            os.utime(reserve_path, None)
            fsync_directory(paths.queue)


def count_staged_jobs(paths: RuntimePaths, *, exclude_job_id: str | None = None) -> int:
    """Count active, queued, and reserved staged jobs for backpressure."""
    if exclude_job_id is not None:
        validate_job_id(exclude_job_id)
    ensure_runtime_layout(paths)
    with queue_operation_lock(paths):
        _cleanup_stale_reservations_locked(paths)
        return _count_staged_jobs_locked(paths, exclude_job_id=exclude_job_id)


def has_staged_jobs(paths: RuntimePaths, *, exclude_job_id: str | None = None) -> bool:
    """Return true when any active, queued, or reserved staged job exists."""
    return count_staged_jobs(paths, exclude_job_id=exclude_job_id) > 0


def _next_ready_sequence_locked(paths: RuntimePaths) -> int:
    sequence_path = paths.queue_sequence
    try:
        raw_sequence = read_control_file(sequence_path, max_bytes=64).decode("utf-8").strip()
        current = int(raw_sequence or "0")
    except FileNotFoundError:
        current = 0
    except ValueError as exc:
        raise ProvisionError(f"invalid staged queue sequence: {sequence_path}") from exc
    except OSError as exc:
        raise ProvisionError(f"cannot read staged queue sequence: {sequence_path}") from exc
    next_sequence = current + 1
    tmp_path = paths.queue / f".sequence.{os.getpid()}"
    tmp_path.write_text(f"{next_sequence}\n", encoding="utf-8")
    tmp_path.chmod(0o660)
    os.replace(tmp_path, sequence_path)
    return next_sequence


def _count_staged_jobs_locked(
    paths: RuntimePaths, *, exclude_job_id: str | None = None
) -> int:
    count = 0
    active_job_ids: set[str] = set()
    try:
        if paths.active.exists():
            active_job_ids = {
                path.name
                for path in paths.active.iterdir()
                if path.is_dir() and path.name != exclude_job_id
            }
            count += len(active_job_ids)
    except PermissionError:
        count += 1
    queued_job_ids: set[str] = set()
    for queued_path in paths.queue.iterdir():
        if queued_path.name.startswith(".") or queued_path.suffix in CONTROL_FILE_SUFFIXES:
            continue
        if queued_path.is_dir():
            try:
                job_id = validate_job_id(queued_path.name)
                if job_id != exclude_job_id:
                    queued_job_ids.add(job_id)
            except ProvisionError:
                continue
    ready_job_ids: set[str] = set()
    for ready_path in paths.queue.glob("*.ready"):
        try:
            job_id = validate_job_id(ready_path.name.removesuffix(".ready"))
        except ProvisionError:
            continue
        if (paths.queue / job_id).exists() and job_id != exclude_job_id:
            ready_job_ids.add(job_id)
    count += len(queued_job_ids | ready_job_ids)
    for reserve_path in paths.queue.glob("*.reserve"):
        try:
            job_id = validate_job_id(reserve_path.name.removesuffix(".reserve"))
        except ProvisionError:
            continue
        if job_id != exclude_job_id and (
            job_id not in active_job_ids
            and job_id not in queued_job_ids
            and job_id not in ready_job_ids
        ):
            count += 1
    return count


def _reservation_sort_key(path: Path) -> tuple[int, float]:
    payload = read_json(path)
    sequence = payload.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence <= 0:
        raise ProvisionError(f"staged reservation missing valid sequence: {path}")
    created_at = payload.get("created_at")
    return sequence, created_at if isinstance(created_at, int | float) else time.time()


def _cleanup_stale_reservations_locked(paths: RuntimePaths) -> None:
    deadline = time.time() - STAGED_RESERVATION_TTL_SECONDS
    removed = False
    for reserve_path in paths.queue.glob("*.reserve"):
        try:
            reserve_stat = reserve_path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(reserve_stat.st_mode) or not stat.S_ISREG(reserve_stat.st_mode):
            _remove_staged_path(reserve_path)
            removed = True
            continue
        if reserve_stat.st_mtime < deadline:
            _remove_staged_path(reserve_path)
            removed = True
    if removed:
        fsync_directory(paths.queue)


def _ready_sequence_for_job_locked(paths: RuntimePaths, job_id: str) -> int | None:
    for path in (paths.queue / f"{job_id}.ready", paths.queue / f"{job_id}.reserve"):
        try:
            return (
                _ready_marker_sort_key(path)[0]
                if path.suffix == ".ready"
                else _reservation_sort_key(path)[0]
            )
        except FileNotFoundError:
            continue
        except ProvisionError:
            continue
    return None


def _has_lower_sequence_reservation_locked(paths: RuntimePaths, sequence: int) -> bool:
    for control_path in [*paths.queue.glob("*.reserve"), *paths.queue.glob("*.ready")]:
        try:
            control_sequence = (
                _ready_marker_sort_key(control_path)[0]
                if control_path.suffix == ".ready"
                else _reservation_sort_key(control_path)[0]
            )
        except ProvisionError:
            _remove_staged_path(control_path)
            fsync_directory(paths.queue)
            continue
        if control_sequence < sequence:
            return True
    return False


def staged_job_waiting_for_turn(paths: RuntimePaths, job_id: str) -> bool:
    """Return true when a queued job is blocked behind active or lower-sequence work."""
    validate_job_id(job_id)
    ensure_runtime_layout(paths)
    with queue_operation_lock(paths):
        if paths.active.exists() and any(path.is_dir() for path in paths.active.iterdir()):
            return True
        sequence = _ready_sequence_for_job_locked(paths, job_id)
        return sequence is not None and _has_lower_sequence_reservation_locked(paths, sequence)


def claim_next_job(paths: RuntimePaths) -> ClaimedJob | None:
    ensure_runtime_layout(paths, for_worker=True)
    with queue_operation_lock(paths):
        return _claim_next_job_locked(paths)


def _claim_next_job_locked(paths: RuntimePaths) -> ClaimedJob | None:
    active_jobs = sorted(path for path in paths.active.iterdir() if path.is_dir())
    if active_jobs:
        return None

    ready_markers = []
    for ready_path in sorted(paths.queue.glob("*.ready")):
        try:
            ready_markers.append((_ready_marker_sort_key(ready_path), ready_path))
        except ProvisionError:
            _remove_staged_path(ready_path)
            fsync_directory(paths.queue)
    for sort_key, ready_path in sorted(ready_markers):
        sequence, _name = sort_key
        if _has_lower_sequence_reservation_locked(paths, sequence):
            return None
        job_id = validate_job_id(ready_path.name.removesuffix(".ready"))
        queued_path = paths.queue / job_id
        try:
            queued_stat = queued_path.lstat()
        except FileNotFoundError:
            _remove_staged_path(ready_path)
            continue
        if stat.S_ISLNK(queued_stat.st_mode) or not stat.S_ISDIR(queued_stat.st_mode):
            _remove_staged_path(ready_path)
            continue
        active_path = paths.active / job_id
        try:
            os.replace(queued_path, active_path)
        except FileNotFoundError:
            continue
        active_stat = active_path.lstat()
        if stat.S_ISLNK(active_stat.st_mode) or not stat.S_ISDIR(active_stat.st_mode):
            raise ProvisionError(f"claimed staged job is not a directory: {active_path}")
        _remove_staged_path(ready_path)
        fsync_directory(paths.queue)
        fsync_directory(paths.active)
        return ClaimedJob(job_id, active_path)
    return None


def _ready_marker_sort_key(path: Path) -> tuple[int, str]:
    payload = read_json(path)
    sequence = payload.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence <= 0:
        raise ProvisionError(f"staged ready marker missing valid sequence: {path}")
    return sequence, path.name


@contextlib.contextmanager
def queue_operation_lock(paths: RuntimePaths):
    lock_file = _open_queue_lock(paths)
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()


def _open_queue_lock(paths: RuntimePaths):
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(paths.queue_lock, flags, 0o660)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ProvisionError(
                f"staged queue lock must not be a symlink: {paths.queue_lock}"
            ) from exc
        raise
    try:
        lock_stat = os.fstat(fd)
        if not stat.S_ISREG(lock_stat.st_mode):
            raise ProvisionError(f"staged queue lock must be a regular file: {paths.queue_lock}")
        if paths.root == DEFAULT_RUNTIME_ROOT and lock_stat.st_uid != 0:
            raise ProvisionError(f"staged queue lock must be root-owned: {paths.queue_lock}")
        return os.fdopen(fd, "r+")
    except Exception:
        os.close(fd)
        raise


def verify_staged_job(
    job: ClaimedJob, paths: RuntimePaths, *, require_active: bool = True
) -> dict[str, Any]:
    if require_active:
        active_root = paths.active.resolve(strict=False)
        job_path = job.path.resolve(strict=False)
        try:
            job_path.relative_to(active_root)
        except ValueError as exc:
            raise ProvisionError(f"staged job path escaped active directory: {job.path}") from exc

    manifest_path = job.path / "manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("version") != MANIFEST_VERSION:
        raise ProvisionError("unsupported staged manifest version")
    if manifest.get("job_id") != job.job_id:
        raise ProvisionError("staged manifest job id mismatch")
    expected_uid = _require_int(manifest, "service_uid")
    expected_gid = _require_int(manifest, "service_gid")
    _verify_job_top_level(job.path, manifest)
    _verify_tree(job.path / "candidate", manifest.get("candidate", []), expected_uid, expected_gid)
    bundle_entries = manifest.get("bundle_files", [])
    if bundle_entries or manifest.get("bundle_files_present") is True:
        _verify_tree(job.path / "bundle-files", bundle_entries, expected_uid, expected_gid)
    elif (job.path / "bundle-files").exists():
        raise ProvisionError("staged job has unexpected bundle-files directory")
    return manifest


def write_result(paths: RuntimePaths, job_id: str, payload: dict[str, Any]) -> Path:
    validate_job_id(job_id)
    result = {"version": RESULT_VERSION, "job_id": job_id, "completed_at": time.time(), **payload}
    path = paths.results / f"{job_id}.json"
    results_stat = _verify_results_directory(
        paths.results, require_root_owner=paths.root == DEFAULT_RUNTIME_ROOT
    )
    if results_stat is None:
        ensure_runtime_layout(paths, for_worker=True)
        results_stat = _verify_results_directory(
            paths.results, require_root_owner=paths.root == DEFAULT_RUNTIME_ROOT
        )
    owner = (results_stat.st_uid, results_stat.st_gid) if os.geteuid() == 0 else None
    write_json_atomic(path, result, mode=0o640, owner=owner)
    return path


def finalize_abandoned_active_jobs(paths: RuntimePaths, reason: str) -> int:
    """Write failed results for claimed jobs left behind by an interrupted worker."""
    ensure_runtime_layout(paths, for_worker=True)
    finalized = 0
    with queue_operation_lock(paths):
        for active_path in sorted(path for path in paths.active.iterdir() if path.is_dir()):
            job_id = validate_job_id(active_path.name)
            if read_result(paths, job_id) is None:
                write_result(paths, job_id, {"status": "failed", "error": reason})
            shutil.rmtree(active_path, ignore_errors=True)
            finalized += 1
        fsync_directory(paths.active)
    return finalized


def read_result(paths: RuntimePaths, job_id: str) -> dict[str, Any] | None:
    validate_job_id(job_id)
    path = paths.results / f"{job_id}.json"
    results_stat = _verify_results_directory(
        paths.results, require_root_owner=paths.root == DEFAULT_RUNTIME_ROOT
    )
    if results_stat is None:
        return None
    try:
        result_stat = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(result_stat.st_mode):
        raise ProvisionError(f"staged result must not be a symlink: {path}")
    if not stat.S_ISREG(result_stat.st_mode):
        raise ProvisionError(f"staged result must be a regular file: {path}")
    if result_stat.st_uid != results_stat.st_uid:
        raise ProvisionError(f"staged result has unexpected owner: {path}")
    if result_stat.st_gid != results_stat.st_gid:
        raise ProvisionError(f"staged result has unexpected group: {path}")
    if result_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ProvisionError(f"staged result must not be group/world writable: {path}")
    result = read_json(path)
    if result.get("version") != RESULT_VERSION or result.get("job_id") != job_id:
        raise ProvisionError(f"invalid staged result: {path}")
    return result


def can_abandon_queued_job(paths: RuntimePaths, job_id: str) -> bool:
    """Return true if a timed-out job has not been claimed by the root worker."""
    validate_job_id(job_id)
    with queue_operation_lock(paths):
        return _job_presence_locked(paths, job_id) == "queued"


def staged_job_presence(paths: RuntimePaths, job_id: str) -> str:
    """Return queued, active, or missing for a staged job under the queue lock."""
    validate_job_id(job_id)
    with queue_operation_lock(paths):
        return _job_presence_locked(paths, job_id)


def abandon_queued_job(paths: RuntimePaths, job_id: str) -> None:
    """Remove a timed-out job that is still queued and has not been claimed."""
    if not try_abandon_queued_job(paths, job_id):
        raise ProvisionError("cannot abandon staged job after privileged apply worker claimed it")


def try_abandon_queued_job(paths: RuntimePaths, job_id: str) -> bool:
    """Atomically remove a queued job if the root worker has not claimed it."""
    validate_job_id(job_id)
    with queue_operation_lock(paths):
        if _job_presence_locked(paths, job_id) != "queued":
            return False
        queued_path = paths.queue / job_id
        ready_path = paths.queue / f"{job_id}.ready"
        _remove_staged_path(ready_path)
        shutil.rmtree(queued_path, ignore_errors=True)
        fsync_directory(paths.queue)
        return True


def _job_presence_locked(paths: RuntimePaths, job_id: str) -> str:
    try:
        if (paths.active / job_id).exists():
            return "active"
    except OSError:
        return "active"
    if (paths.queue / job_id).exists() or (paths.queue / f"{job_id}.ready").exists():
        return "queued"
    return "missing"


def _verify_results_directory(
    path: Path, *, require_root_owner: bool = False
) -> os.stat_result | None:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ProvisionError(f"cannot stat staged results directory: {path}") from exc
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISDIR(path_stat.st_mode):
        raise ProvisionError(f"staged results path must be a directory: {path}")
    if require_root_owner and path_stat.st_uid != 0:
        raise ProvisionError(f"staged results directory must be root-owned: {path}")
    if path_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ProvisionError(f"staged results directory must not be group/world writable: {path}")
    return path_stat


def cleanup_claimed_job(job: ClaimedJob) -> None:
    shutil.rmtree(job.path, ignore_errors=True)


def _remove_staged_path(path: Path) -> None:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISDIR(path_stat.st_mode) and not stat.S_ISLNK(path_stat.st_mode):
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def fsync_directory(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _verify_job_top_level(job_path: Path, manifest: dict[str, Any]) -> None:
    allowed = {"manifest.json", "candidate"}
    if manifest.get("bundle_files") or manifest.get("bundle_files_present") is True:
        allowed.add("bundle-files")
    actual = {child.name for child in job_path.iterdir()}
    unexpected = actual - allowed
    if unexpected:
        raise ProvisionError(
            "staged job contains unexpected top-level entries: " + ", ".join(sorted(unexpected))
        )
    _verify_path_metadata(
        job_path / "candidate",
        _require_int(manifest, "service_uid"),
        _require_int(manifest, "service_gid"),
    )
    if not (job_path / "candidate").is_dir():
        raise ProvisionError("staged job missing candidate directory")


def _verify_tree(
    root: Path, expected_entries: Any, expected_uid: int, expected_gid: int
) -> None:
    if not isinstance(expected_entries, list):
        raise ProvisionError("staged manifest tree entries must be a list")
    expected = {_entry_key(entry): entry for entry in expected_entries}
    _verify_path_metadata(root, expected_uid, expected_gid)
    actual_entries = tree_manifest(root)
    actual = {_entry_key(entry): entry for entry in actual_entries}
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        unexpected = sorted(set(actual) - set(expected))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(path for path, _type in missing))
        if unexpected:
            parts.append("unexpected: " + ", ".join(path for path, _type in unexpected))
        raise ProvisionError("staged tree does not match manifest (" + "; ".join(parts) + ")")

    for key, expected_entry in expected.items():
        rel_path, entry_type = key
        actual_entry = actual[key]
        path = root / rel_path
        _verify_path_metadata(path, expected_uid, expected_gid)
        if actual_entry.get("mode") != expected_entry.get("mode"):
            raise ProvisionError(f"staged path mode changed: {path}")
        if entry_type == "file":
            if actual_entry.get("size") != expected_entry.get("size"):
                raise ProvisionError(f"staged file size changed: {path}")
            if actual_entry.get("sha256") != expected_entry.get("sha256"):
                raise ProvisionError(f"staged file hash changed: {path}")


def _verify_path_metadata(path: Path, expected_uid: int, expected_gid: int) -> None:
    try:
        path_stat = path.lstat()
    except OSError as exc:
        raise ProvisionError(f"cannot stat staged path: {path}") from exc
    if stat.S_ISLNK(path_stat.st_mode):
        raise ProvisionError(f"staged path must not be a symlink: {path}")
    if path_stat.st_uid not in {0, expected_uid}:
        raise ProvisionError(f"staged path has unexpected owner: {path}")
    if path_stat.st_gid not in {0, expected_gid}:
        raise ProvisionError(f"staged path has unexpected group: {path}")
    if path_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ProvisionError(f"staged path must not be group/world writable: {path}")


def _entry_key(entry: Any) -> tuple[str, str]:
    if not isinstance(entry, dict):
        raise ProvisionError("staged manifest tree entry must be an object")
    path = validate_relative_path(entry.get("path", ""))
    entry_type = entry.get("type")
    if entry_type not in {"dir", "file"}:
        raise ProvisionError(f"invalid staged manifest entry type for {path}: {entry_type!r}")
    mode = entry.get("mode")
    if not isinstance(mode, int) or isinstance(mode, bool) or mode < 0 or mode > 0o7777:
        raise ProvisionError(f"invalid staged manifest mode for {path}")
    if entry_type == "file":
        size = entry.get("size")
        digest = entry.get("sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ProvisionError(f"invalid staged manifest size for {path}")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ProvisionError(f"invalid staged manifest hash for {path}")
    return path, entry_type


def _require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ProvisionError(f"staged manifest {key} must be a non-negative integer")
    return value
