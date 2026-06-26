"""Bundle import: tar extraction, file placement, token substitution."""

import os
import pwd
import shutil
import stat
import subprocess
import tarfile
import tempfile
import threading
from pathlib import Path

from atomixos_provision.config import provision_error

APP_RUNTIME_USER = "appsvc"

__all__ = [
    "copy_bundle_files",
    "detect_bundle_kind",
    "extract_bundle_archive",
    "import_bundle_bytes",
    "prepare_source_bytes",
    "prepare_source_path",
    "stage_bundle_files",
]

# --- Constants ---

GZIP_MAGIC = b"\x1f\x8b"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
GZIP_BIN = os.environ.get("ATOMIXOS_GZIP", "gzip") if os.geteuid() == os.getuid() else "gzip"
ZSTD_BIN = os.environ.get("ATOMIXOS_ZSTD", "zstd") if os.geteuid() == os.getuid() else "zstd"
MAX_SOURCE_BYTES = (
    int(os.environ.get("ATOMIXOS_MAX_CONFIG_UPLOAD_BYTES", str(32 * 1024 * 1024)))
    if os.geteuid() == os.getuid()
    else 32 * 1024 * 1024
)
MAX_DECOMPRESSED_BYTES = (
    int(os.environ.get("ATOMIXOS_MAX_BUNDLE_DECOMPRESSED_BYTES", str(256 * 1024 * 1024)))
    if os.geteuid() == os.getuid()
    else 256 * 1024 * 1024
)
MAX_BUNDLE_MEMBERS = (
    int(os.environ.get("ATOMIXOS_MAX_BUNDLE_MEMBERS", "4096"))
    if os.geteuid() == os.getuid()
    else 4096
)
MAX_BUNDLE_MEMBER_BYTES = (
    int(os.environ.get("ATOMIXOS_MAX_BUNDLE_MEMBER_BYTES", str(64 * 1024 * 1024)))
    if os.geteuid() == os.getuid()
    else 64 * 1024 * 1024
)
DECOMPRESS_TIMEOUT_SECONDS = (
    int(os.environ.get("ATOMIXOS_DECOMPRESS_TIMEOUT_SECONDS", "30"))
    if os.geteuid() == os.getuid()
    else 30
)
OPEN_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _open_dir_no_follow(path: Path) -> int:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | OPEN_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        message = f"failed to open bundle directory without following symlinks: {path}"
        raise provision_error(message) from exc
    try:
        fd_stat = os.fstat(fd)
        if not stat.S_ISDIR(fd_stat.st_mode):
            raise provision_error(f"bundle files entry must be a directory: {path}")
        return fd
    except Exception:
        os.close(fd)
        raise


def _snapshot_files_source(files_source: Path, destination: Path) -> None:
    root_fd = _open_dir_no_follow(files_source)
    try:
        _snapshot_dir(root_fd, files_source, destination)
    finally:
        os.close(root_fd)


def _snapshot_dir(source_fd: int, source_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    destination.chmod(0o755)
    for name in sorted(os.listdir(source_fd)):
        if name in {"", ".", ".."}:
            raise provision_error(f"invalid bundle files entry: {name!r}")
        child_path = source_path / name
        try:
            child_stat = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
        except OSError as exc:
            raise provision_error(f"cannot stat bundle files entry: {child_path}") from exc
        target_path = destination / name
        if stat.S_ISLNK(child_stat.st_mode):
            raise provision_error(f"bundle files entry must not be a symlink: {child_path}")
        if stat.S_ISDIR(child_stat.st_mode):
            child_fd = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | OPEN_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=source_fd,
            )
            try:
                confirmed = os.fstat(child_fd)
                if not stat.S_ISDIR(confirmed.st_mode):
                    raise provision_error(f"bundle files entry must be a directory: {child_path}")
                _snapshot_dir(child_fd, child_path, target_path)
            finally:
                os.close(child_fd)
            continue
        if not stat.S_ISREG(child_stat.st_mode):
            raise provision_error(f"bundle files entry must be a regular file: {child_path}")
        file_fd = os.open(
            name,
            os.O_RDONLY | OPEN_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            dir_fd=source_fd,
        )
        try:
            confirmed = os.fstat(file_fd)
            if not stat.S_ISREG(confirmed.st_mode):
                raise provision_error(f"bundle files entry must be a regular file: {child_path}")
            with os.fdopen(file_fd, "rb") as source_file, target_path.open("wb") as output:
                file_fd = -1
                shutil.copyfileobj(source_file, output)
            target_path.chmod(0o644)
        finally:
            if file_fd >= 0:
                os.close(file_fd)


# --- Detection ---


def detect_bundle_kind(source_bytes: bytes, filename: str = "") -> str | None:
    """Detect bundle format from magic bytes or filename extension."""
    lowered = filename.lower()
    if lowered.endswith((".tar.gz", ".tgz")) or source_bytes.startswith(GZIP_MAGIC):
        return "tar.gz"
    if lowered.endswith((".tar.zst", ".tar.zstd", ".tzst")) or source_bytes.startswith(ZSTD_MAGIC):
        return "tar.zst"
    return None


# --- Validation ---


def validate_bundle_member(name: str) -> None:
    """Validate a tar archive member path for safety."""
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or name == "":
        message = f"invalid bundle member path: {name!r}"
        raise provision_error(message)


def validate_source_size(source_bytes: bytes) -> None:
    """Reject uploads that exceed the configured compressed/plain size limit."""
    if len(source_bytes) > MAX_SOURCE_BYTES:
        message = f"config upload exceeds {MAX_SOURCE_BYTES} byte limit"
        raise provision_error(message)


def validate_decompressed_size(decompressed: bytes) -> None:
    """Reject bundles that exceed the configured decompressed size limit."""
    if len(decompressed) > MAX_DECOMPRESSED_BYTES:
        message = f"bundle exceeds {MAX_DECOMPRESSED_BYTES} byte decompressed limit"
        raise provision_error(message)


def _decompress_to_tempfile(command: list[str], source_bytes: bytes, label: str) -> Path:
    with tempfile.NamedTemporaryFile(delete=False) as output:
        output_path = Path(output.name)
    total = 0
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert proc.stdin is not None
        assert proc.stdout is not None
        try:
            # Write stdin in a daemon thread to avoid deadlock when pipe
            # buffers fill (subprocess blocks on stdout while we block on
            # stdin write).
            def _feed_stdin() -> None:
                try:
                    proc.stdin.write(source_bytes)  # type: ignore[union-attr]
                finally:
                    proc.stdin.close()  # type: ignore[union-attr]

            writer = threading.Thread(target=_feed_stdin, daemon=True)
            writer.start()
            with output_path.open("ab") as output_file:
                while True:
                    chunk = proc.stdout.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_DECOMPRESSED_BYTES:
                        proc.kill()
                        proc.wait(timeout=DECOMPRESS_TIMEOUT_SECONDS)
                        message = (
                            f"bundle exceeds {MAX_DECOMPRESSED_BYTES} byte decompressed limit"
                        )
                        raise provision_error(message)
                    output_file.write(chunk)
            writer.join(timeout=DECOMPRESS_TIMEOUT_SECONDS)
            stderr = proc.stderr.read()
            returncode = proc.wait(timeout=DECOMPRESS_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            proc.wait()
            writer.join(timeout=5)
            message = f"timed out decompressing {label} bundle"
            raise provision_error(message) from exc
        finally:
            proc.stdout.close()
            proc.stderr.close()
        if returncode != 0:
            detail_text = stderr.decode("utf-8", errors="replace").strip()
            detail = f": {detail_text}" if detail_text else ""
            message = f"failed to decompress {label} bundle{detail}"
            raise provision_error(message)
        return output_path
    except FileNotFoundError as exc:
        output_path.unlink(missing_ok=True)
        tool = command[0]
        message = f"{tool} is required to import {label} bundles"
        raise provision_error(message) from exc
    except Exception:
        output_path.unlink(missing_ok=True)
        raise


def validate_bundle_layout(bundle_root: Path) -> None:
    """Validate that extracted bundle has expected structure."""
    allowed_entries = {"config.toml", "files"}
    actual_entries = {entry.name for entry in bundle_root.iterdir()}
    if "config.toml" not in actual_entries:
        message = "bundle must contain config.toml at the top level"
        raise provision_error(message)

    unexpected = actual_entries - allowed_entries
    if unexpected:
        names = ", ".join(sorted(unexpected))
        message = f"bundle contains unsupported top-level entries: {names}"
        raise provision_error(message)

    files_dir = bundle_root / "files"
    if files_dir.exists() and not files_dir.is_dir():
        message = "bundle entry 'files' must be a directory"
        raise provision_error(message)


def _validate_no_symlinks(path: Path) -> None:
    for current in [path, *path.rglob("*")]:
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            message = f"cannot stat bundle files entry: {current}"
            raise provision_error(message) from exc
        if stat.S_ISLNK(mode):
            raise provision_error(f"bundle files entry must not be a symlink: {current}")


def _copy_regular_file_no_follow(source: Path, destination: Path) -> None:
    try:
        source_fd = os.open(source, os.O_RDONLY | OPEN_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
    except OSError as exc:
        message = f"failed to open bundle file without following symlinks: {source}"
        raise provision_error(message) from exc
    try:
        source_stat = os.fstat(source_fd)
        if not stat.S_ISREG(source_stat.st_mode):
            raise provision_error(f"bundle files entry must be a regular file: {source}")
        with os.fdopen(source_fd, "rb") as source_file, destination.open("wb") as output:
            source_fd = -1
            shutil.copyfileobj(source_file, output)
    finally:
        if source_fd >= 0:
            os.close(source_fd)


def _remove_bundle_files_target(target: Path) -> None:
    try:
        target_mode = target.lstat().st_mode
    except FileNotFoundError:
        return
    if stat.S_ISDIR(target_mode):
        shutil.rmtree(target)
        return
    target.unlink()


def _grant_app_runtime_ownership(path: Path, uid: int, gid: int) -> None:
    for current in [path, *path.rglob("*")]:
        current_stat = current.lstat()
        if stat.S_ISLNK(current_stat.st_mode):
            raise provision_error(f"bundle files entry must not be a symlink: {current}")
        os.chown(current, uid, gid, follow_symlinks=False)
        if stat.S_ISDIR(current_stat.st_mode):
            current.chmod(0o700)
        elif stat.S_ISREG(current_stat.st_mode):
            current.chmod(0o600)
        else:
            raise provision_error(f"bundle files entry must be a regular file: {current}")


# --- Extraction ---


def extract_bundle_archive(source_bytes: bytes, filename: str, destination: Path) -> None:
    """Extract a compressed tar bundle to the destination directory."""
    bundle_kind = detect_bundle_kind(source_bytes, filename)
    if bundle_kind == "tar.gz":
        decompressed_path = _decompress_to_tempfile([GZIP_BIN, "-dc"], source_bytes, ".tar.gz")
    elif bundle_kind == "tar.zst":
        decompressed_path = _decompress_to_tempfile([ZSTD_BIN, "-dcq"], source_bytes, ".tar.zst")
    else:
        message = "supported bundle formats are .tar.gz, .tgz, .tar.zst, .tar.zstd, and .tzst"
        raise provision_error(message)

    try:
        with tarfile.open(decompressed_path, mode="r:") as archive:
            members = archive.getmembers()
            if len(members) > MAX_BUNDLE_MEMBERS:
                message = f"bundle exceeds {MAX_BUNDLE_MEMBERS} member limit"
                raise provision_error(message)
            for member in members:
                validate_bundle_member(member.name)
                if member.name == ".":
                    if member.isdir():
                        continue
                    message = "bundle member '.' must be a directory"
                    raise provision_error(message)
                target = destination / member.name
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    target.chmod(0o755)
                    continue
                if not member.isfile():
                    message = f"unsupported bundle member type: {member.name}"
                    raise provision_error(message)
                if member.size > MAX_BUNDLE_MEMBER_BYTES:
                    message = (
                        f"bundle member {member.name!r} exceeds "
                        f"{MAX_BUNDLE_MEMBER_BYTES} byte limit"
                    )
                    raise provision_error(message)

                target.parent.mkdir(parents=True, exist_ok=True)
                extracted = archive.extractfile(member)
                if extracted is None:
                    message = f"failed to read bundle member: {member.name}"
                    raise provision_error(message)
                with extracted, target.open("wb") as output:
                    shutil.copyfileobj(extracted, output)
                target.chmod(0o644)
    except tarfile.TarError as exc:
        raise provision_error("failed to read bundle archive") from exc
    finally:
        decompressed_path.unlink(missing_ok=True)


# --- Source Preparation ---


def prepare_bundle_from_bytes(
    source_bytes: bytes, filename: str = ""
) -> tuple[tempfile.TemporaryDirectory, Path, Path]:
    """Extract a bundle archive and return (tmpdir, config_path, files_path)."""
    tmpdir = tempfile.TemporaryDirectory()
    bundle_root = Path(tmpdir.name)
    extract_bundle_archive(source_bytes, filename, bundle_root)
    validate_bundle_layout(bundle_root)
    return tmpdir, bundle_root / "config.toml", bundle_root / "files"


def prepare_source_path(
    source_path: Path,
) -> tuple[tempfile.TemporaryDirectory | None, Path, Path | None]:
    """Prepare a source file for import.

    Returns (tmpdir_or_None, config_path, files_path_or_None).
    """
    if source_path.suffix == ".toml":
        if source_path.stat().st_size > MAX_SOURCE_BYTES:
            message = f"config upload exceeds {MAX_SOURCE_BYTES} byte limit"
            raise provision_error(message)
        return None, source_path, None

    source_bytes = source_path.read_bytes()
    validate_source_size(source_bytes)
    bundle_kind = detect_bundle_kind(source_bytes, source_path.name)
    if bundle_kind is None:
        message = (
            "supported import inputs are config.toml, .tar.gz/.tgz, and .tar.zst/.tar.zstd/.tzst"
        )
        raise provision_error(message)
    return prepare_bundle_from_bytes(source_bytes, source_path.name)


def prepare_source_bytes(
    source_bytes: bytes, filename: str = ""
) -> tuple[tempfile.TemporaryDirectory, Path, Path | None]:
    """Prepare raw bytes for import (bundle or plain TOML).

    Returns (tmpdir, config_path, files_path_or_None).
    """
    validate_source_size(source_bytes)
    bundle_kind = detect_bundle_kind(source_bytes, filename)
    if bundle_kind is not None:
        return prepare_bundle_from_bytes(source_bytes, filename)

    tmpdir = tempfile.TemporaryDirectory()
    config_path = Path(tmpdir.name) / "config.toml"
    config_path.write_bytes(source_bytes)
    return tmpdir, config_path, None


# --- File Placement ---


def copy_bundle_files(files_source: Path | None, config_root: Path) -> None:
    """Copy extracted bundle files into config_root/files/."""
    target = config_root / "files"
    if files_source is None or not files_source.exists():
        _remove_bundle_files_target(target)
        return
    try:
        app_user = pwd.getpwnam(APP_RUNTIME_USER)
        app_uid = app_user.pw_uid
        app_gid = app_user.pw_gid
    except KeyError as exc:
        message = f"runtime user not found for bundle files: {APP_RUNTIME_USER}"
        raise provision_error(message) from exc
    config_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".atomixos-files-", dir=config_root) as staging_dir:
        staging_root = Path(staging_dir)
        staging_root.chmod(0o700)
        staging_target = staging_root / "files"
        _snapshot_files_source(files_source, staging_target)
        _grant_app_runtime_ownership(staging_target, app_uid, app_gid)
        _remove_bundle_files_target(target)
        os.replace(staging_target, target)


def stage_bundle_files(files_source: Path | None, destination: Path) -> None:
    """Copy validated bundle files into an unprivileged staging tree."""
    if destination.exists():
        _remove_bundle_files_target(destination)
    if files_source is None or not files_source.exists():
        return
    _snapshot_files_source(files_source, destination)


# --- High-Level Import ---


def import_bundle_bytes(
    source_bytes: bytes,
    filename: str,
    config_root: Path,
) -> tuple[Path, Path | None, tempfile.TemporaryDirectory]:
    """Import raw bytes as a bundle or plain config.

    Returns (config_path, files_path_or_None, tmpdir).
    Caller must cleanup tmpdir when done.
    """
    tmpdir, config_path, files_path = prepare_source_bytes(source_bytes, filename)
    return config_path, files_path, tmpdir
