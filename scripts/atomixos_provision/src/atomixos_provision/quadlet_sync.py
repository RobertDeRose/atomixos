"""Copy rendered Quadlet units to rootful/rootless target directories."""

import json
import os
import shutil
import tempfile
from pathlib import Path

from atomixos_provision.config import provision_error
from atomixos_provision.quadlet import QUADLET_SUFFIXES, RUNTIME_METADATA_FILENAME

__all__ = ["load_runtime_metadata", "sync_quadlet_units"]

MANAGED_MANIFEST = ".atomixos-managed-quadlets.json"


def load_runtime_metadata(config_root: Path) -> dict:
    """Load quadlet-runtime.json from the config root."""
    metadata_path = config_root / RUNTIME_METADATA_FILENAME
    if not metadata_path.exists():
        message = f"missing runtime metadata: {metadata_path}"
        raise provision_error(message)

    try:
        metadata = json.loads(metadata_path.read_text())
    except json.JSONDecodeError as exc:
        message = f"invalid runtime metadata in {metadata_path}: {exc}"
        raise provision_error(message) from exc

    if not isinstance(metadata, dict) or not isinstance(metadata.get("units"), list):
        message = f"invalid runtime metadata structure in {metadata_path}"
        raise provision_error(message)
    return metadata


def validate_runtime_filename(filename: str) -> None:
    """Validate a rendered Quadlet filename from runtime metadata."""
    path = Path(filename)
    if (
        not filename
        or path.name != filename
        or path.is_absolute()
        or filename in {".", ".."}
        or path.suffix not in QUADLET_SUFFIXES
    ):
        message = f"invalid runtime unit filename: {filename!r}"
        raise provision_error(message)


def _fsync_directory(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _copy_unit_atomic(source: Path, destination: Path) -> None:
    fd, tmp_path = tempfile.mkstemp(
        dir=str(destination.parent),
        prefix=f".{destination.name}.",
    )
    closed = False
    try:
        with source.open("rb") as src, os.fdopen(fd, "wb") as dst:
            closed = True
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        tmp = Path(tmp_path)
        tmp.chmod(0o644)
        tmp.rename(destination)
        _fsync_directory(destination.parent)
    except BaseException:
        if not closed:
            os.close(fd)
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _load_managed_manifest(target: Path) -> set[str]:
    manifest = target / MANAGED_MANIFEST
    if not manifest.exists():
        return set()
    try:
        data = json.loads(manifest.read_text())
    except json.JSONDecodeError as exc:
        message = f"invalid managed quadlet manifest: {manifest}"
        raise provision_error(message) from exc
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        message = f"invalid managed quadlet manifest structure: {manifest}"
        raise provision_error(message)
    managed = set(data)
    for filename in managed:
        validate_runtime_filename(filename)
    return managed


def _write_managed_manifest(target: Path, filenames: set[str]) -> None:
    manifest = target / MANAGED_MANIFEST
    fd, tmp_path = tempfile.mkstemp(dir=str(target), prefix=f".{MANAGED_MANIFEST}.")
    closed = False
    try:
        with os.fdopen(fd, "w") as tmp:
            closed = True
            tmp.write(json.dumps(sorted(filenames), indent=2) + "\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        tmp = Path(tmp_path)
        tmp.chmod(0o644)
        tmp.rename(manifest)
        _fsync_directory(target)
    except BaseException:
        if not closed:
            os.close(fd)
        Path(tmp_path).unlink(missing_ok=True)
        raise


def sync_quadlet_units(
    config_root: Path,
    rootful_target: Path,
    rootless_target: Path | None = None,
) -> None:
    """Synchronize rendered Quadlet units to target directories.

    Copies desired units from config_root/quadlet/ to the appropriate target
    directory and removes stale units no longer in the runtime metadata.
    """
    source = config_root / "quadlet"
    metadata = load_runtime_metadata(config_root)
    units_by_mode: dict[str, set[str]] = {"rootful": set(), "rootless": set()}

    for unit in metadata["units"]:
        if not isinstance(unit, dict):
            message = "invalid runtime unit entry"
            raise provision_error(message)
        filename = unit.get("filename")
        mode = unit.get("mode")
        if not isinstance(filename, str) or mode not in units_by_mode:
            message = "invalid runtime unit metadata"
            raise provision_error(message)
        validate_runtime_filename(filename)
        units_by_mode[mode].add(filename)

    # Sync rootful units
    rootful_target.mkdir(parents=True, exist_ok=True)
    existing_rootful = _load_managed_manifest(rootful_target)
    desired_rootful = units_by_mode["rootful"]

    for filename in desired_rootful:
        unit_file = source / filename
        _copy_unit_atomic(unit_file, rootful_target / filename)

    for stale in existing_rootful - desired_rootful:
        (rootful_target / stale).unlink(missing_ok=True)
    _write_managed_manifest(rootful_target, desired_rootful)

    # Sync rootless units
    if rootless_target is None:
        if units_by_mode["rootless"]:
            message = "rootless target path is required when rootless units are present"
            raise provision_error(message)
        return

    rootless_target.mkdir(parents=True, exist_ok=True)
    existing_rootless = _load_managed_manifest(rootless_target)
    desired_rootless = units_by_mode["rootless"]

    for filename in desired_rootless:
        unit_file = source / filename
        _copy_unit_atomic(unit_file, rootless_target / filename)

    for stale in existing_rootless - desired_rootless:
        (rootless_target / stale).unlink(missing_ok=True)
    _write_managed_manifest(rootless_target, desired_rootless)
