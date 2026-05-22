"""Activation script runner, service health checks, and rollback."""

import json
import os
import pwd
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

__all__ = [
    "activate_services",
    "atomic_promote",
    "atomic_promote_initial",
    "check_required_services",
    "cleanup_rollback",
    "complete_reapply",
    "discard_initial_config",
    "recover_config_root",
    "restore_rollback",
]

# --- Constants ---

BOOTSTRAP_ACTIVATION_ENV = "ATOMIXOS_BOOTSTRAP_ACTIVATION"
BOOTSTRAP_ACTIVATION_TIMEOUT_SECONDS = 300
APP_RUNTIME_USER = "appsvc"


class ProgressReporter(Protocol):
    def set_stage(
        self, name: str, detail: str | None = None, **fields: str | int | float | bool
    ) -> None: ...


CANDIDATE_SUFFIX = "-candidate"
ROLLBACK_SUFFIX = "-rollback"
PROMOTION_MARKER = ".atomixos-promotion-pending"


# --- Path Helpers ---


def _fsync_directory(path: Path) -> None:
    """Flush directory metadata to disk to ensure rename durability."""
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_file(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_tree(path: Path) -> None:
    """Flush file contents and directory metadata before publishing a tree."""
    for child in path.iterdir():
        if child.is_dir():
            _fsync_tree(child)
        elif child.is_file():
            _fsync_file(child)
    _fsync_directory(path)


def promotion_marker_path(config_root: Path) -> Path:
    """Get the path to the promotion marker file."""
    return config_root.parent / f"{config_root.name}{PROMOTION_MARKER}"


def candidate_root_path(config_root: Path) -> Path:
    return config_root.parent / (config_root.name + CANDIDATE_SUFFIX)


def rollback_root_path(config_root: Path) -> Path:
    return config_root.parent / (config_root.name + ROLLBACK_SUFFIX)


# --- Managed State ---


def carry_forward_managed_state(previous_root: Path, candidate_root: Path) -> None:
    """Copy managed-users.json from previous config to candidate."""
    previous_state = previous_root / "managed-users.json"
    if not previous_state.exists():
        return
    target_state = candidate_root / "managed-users.json"
    shutil.copyfile(previous_state, target_state)
    target_state.chmod(0o600)


def read_managed_state(config_root: Path) -> set[str]:
    """Read the set of managed user names from config root."""
    state_path = config_root / "managed-users.json"
    if not state_path.exists():
        return set()
    try:
        data = json.loads(state_path.read_text())
    except (json.JSONDecodeError, OSError):
        return set()
    if not isinstance(data, list):
        return set()
    return {name for name in data if isinstance(name, str)}


def write_managed_state(config_root: Path, names: set[str]) -> None:
    """Write the managed user names set to config root."""
    state_path = config_root / "managed-users.json"
    state_path.write_text(json.dumps(sorted(names), indent=2) + "\n")
    state_path.chmod(0o600)


# --- Crash Recovery ---


def recover_config_root(config_root: Path) -> None:
    """Recover from interrupted promotion or activation."""
    rollback_root = rollback_root_path(config_root)
    candidate_root = candidate_root_path(config_root)
    marker_path = promotion_marker_path(config_root)

    if marker_path.exists() and rollback_root.exists():
        if config_root.exists():
            shutil.rmtree(config_root)
            rollback_root.rename(config_root)
            if candidate_root.exists():
                shutil.rmtree(candidate_root)
            marker_path.unlink(missing_ok=True)
            _fsync_directory(config_root.parent)
            return
        rollback_root.rename(config_root)
        if candidate_root.exists():
            shutil.rmtree(candidate_root)
        marker_path.unlink(missing_ok=True)
        _fsync_directory(config_root.parent)
        return

    if marker_path.exists() and not rollback_root.exists():
        if config_root.exists() and (config_root / "config.toml").exists():
            if candidate_root.exists():
                shutil.rmtree(candidate_root)
            marker_path.unlink(missing_ok=True)
            _fsync_directory(config_root.parent)
            return
        if config_root.exists():
            shutil.rmtree(config_root)
        if candidate_root.exists():
            shutil.rmtree(candidate_root)
        marker_path.unlink(missing_ok=True)
        _fsync_directory(config_root.parent)
        return

    if (config_root / "config.toml").exists():
        if candidate_root.exists():
            shutil.rmtree(candidate_root)
        return

    if candidate_root.exists():
        shutil.rmtree(candidate_root)
        return

    if rollback_root.exists():
        rollback_root.rename(config_root)


# --- Atomic Promotion ---


def atomic_promote(config_root: Path, candidate_root: Path) -> None:
    """Atomically promote candidate to active, preserving rollback.

    Uses fsync on the parent directory after each critical rename to ensure
    crash-safety on journaling filesystems.
    """
    rollback_root = rollback_root_path(config_root)
    parent_dir = config_root.parent

    if rollback_root.exists():
        shutil.rmtree(rollback_root)

    _fsync_tree(candidate_root)
    promotion_marker_path(config_root).write_text("pending\n")
    _fsync_directory(parent_dir)

    config_root.rename(rollback_root)
    _fsync_directory(parent_dir)

    candidate_root.rename(config_root)
    _fsync_directory(parent_dir)


def atomic_promote_initial(config_root: Path, candidate_root: Path) -> None:
    """Promote an initial candidate root without requiring an active root."""
    parent_dir = config_root.parent
    rollback_root = rollback_root_path(config_root)

    if rollback_root.exists():
        shutil.rmtree(rollback_root)
        _fsync_directory(parent_dir)

    _fsync_tree(candidate_root)
    promotion_marker_path(config_root).write_text("pending\n")
    _fsync_directory(parent_dir)

    if config_root.exists():
        shutil.rmtree(config_root)
        _fsync_directory(parent_dir)
    candidate_root.rename(config_root)
    _fsync_directory(parent_dir)


# --- Rollback ---


def cleanup_rollback(config_root: Path) -> None:
    """Remove rollback state after successful activation."""
    rollback_root = rollback_root_path(config_root)
    if rollback_root.exists():
        shutil.rmtree(rollback_root)
    promotion_marker_path(config_root).unlink(missing_ok=True)
    _fsync_directory(config_root.parent)


def discard_initial_config(config_root: Path) -> None:
    """Remove a failed initial config so the device remains in bootstrap mode."""
    candidate_root = candidate_root_path(config_root)
    rollback_root = rollback_root_path(config_root)
    marker_path = promotion_marker_path(config_root)
    if config_root.exists():
        shutil.rmtree(config_root)
    if candidate_root.exists():
        shutil.rmtree(candidate_root)
    if rollback_root.exists():
        shutil.rmtree(rollback_root)
    marker_path.unlink(missing_ok=True)
    _fsync_directory(config_root.parent)


def restore_rollback(config_root: Path) -> bool:
    """Restore previous config from rollback. Returns True if restored."""
    rollback_root = rollback_root_path(config_root)
    marker_path = promotion_marker_path(config_root)

    if not rollback_root.exists():
        marker_path.unlink(missing_ok=True)
        _fsync_directory(config_root.parent)
        return False

    failed_managed = read_managed_state(config_root)
    rollback_managed = read_managed_state(rollback_root)

    if config_root.exists():
        shutil.rmtree(config_root)
    rollback_root.rename(config_root)
    _fsync_directory(config_root.parent)
    merged_managed = rollback_managed | failed_managed
    if merged_managed:
        write_managed_state(config_root, merged_managed)
    marker_path.unlink(missing_ok=True)
    _fsync_directory(config_root.parent)
    return True


# --- Activation ---


def activate_services(progress: ProgressReporter | None = None) -> list[str]:
    """Run the activation script. Returns list of failure messages."""
    command = os.environ.get(BOOTSTRAP_ACTIVATION_ENV)
    if not command:
        if progress:
            progress.set_stage("activate", "no activation hook configured")
        return []
    command_path = Path(command)
    if not command_path.is_absolute():
        return [f"activation command must be an absolute path, got: {command}"]
    if not command_path.is_file():
        return [f"activation command not found: {command}"]
    if progress:
        progress.set_stage("activate", "running activation hook")
    try:
        result = subprocess.run(
            [command],
            capture_output=True,
            text=True,
            timeout=BOOTSTRAP_ACTIVATION_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            return [f"activation script failed (exit {result.returncode}): {stderr[:200]}"]
    except subprocess.TimeoutExpired:
        return [f"activation script timed out after {BOOTSTRAP_ACTIVATION_TIMEOUT_SECONDS}s"]
    except FileNotFoundError:
        return ["activation script not found"]
    return []


def _load_runtime_unit_modes(config_root: Path) -> dict[str, str]:
    """Load runtime metadata to determine service modes."""
    metadata_path = config_root / "quadlet-runtime.json"
    if not metadata_path.exists():
        return {}
    try:
        metadata = json.loads(metadata_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    units = metadata.get("units", [])
    return {
        unit.get("service", ""): unit.get("mode", "rootful")
        for unit in units
        if isinstance(unit, dict)
    }


def _load_runtime_units(config_root: Path) -> list[dict[str, str]]:
    """Load rendered Quadlet runtime unit metadata."""
    metadata_path = config_root / "quadlet-runtime.json"
    if not metadata_path.exists():
        return []
    try:
        metadata = json.loads(metadata_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    units = metadata.get("units", [])
    return [unit for unit in units if isinstance(unit, dict)]


def _check_rootless_service(service: str) -> subprocess.CompletedProcess:
    """Check if a rootless user service is active."""
    try:
        uid = pwd.getpwnam(APP_RUNTIME_USER).pw_uid
    except KeyError:
        return subprocess.CompletedProcess([], 1)
    runtime_dir = f"/run/user/{uid}"
    return subprocess.run(
        [
            "runuser",
            "-u",
            APP_RUNTIME_USER,
            "--",
            "env",
            f"HOME=/var/lib/{APP_RUNTIME_USER}",
            f"XDG_RUNTIME_DIR={runtime_dir}",
            f"DBUS_SESSION_BUS_ADDRESS=unix:path={runtime_dir}/bus",
            "systemctl",
            "--user",
            "is-active",
            "--quiet",
            service,
        ],
        timeout=10,
    )


def _check_service(service: str, mode: str) -> subprocess.CompletedProcess:
    if mode == "rootless":
        return _check_rootless_service(service)
    return subprocess.run(["systemctl", "is-active", "--quiet", service], timeout=10)


def report_runtime_services(
    config_root: Path, progress: ProgressReporter | None = None
) -> dict[str, str]:
    """Report status for every rendered runtime unit without failing the apply."""
    statuses: dict[str, str] = {}
    for unit in _load_runtime_units(config_root):
        service = unit.get("service", "")
        if not service:
            continue
        mode = unit.get("mode", "rootful")
        try:
            result = _check_service(service, mode)
            status = "running" if result.returncode == 0 else "failed"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            status = "unknown"
        statuses[service] = status
        if progress:
            progress.set_stage(
                "service-status",
                f"{service} ({mode}) is {status}",
                service=service,
                mode=mode,
                status=status,
            )
    return statuses


def report_runtime_deploy_start(
    config_root: Path, progress: ProgressReporter | None = None
) -> None:
    """Report the units that activation is about to deploy."""
    if not progress:
        return
    for unit in _load_runtime_units(config_root):
        service = unit.get("service", "")
        if not service:
            continue
        mode = unit.get("mode", "rootful")
        filename = unit.get("filename", "")
        status = "building" if filename.endswith(".build") else "starting"
        progress.set_stage(
            "service-deploy",
            f"{service} ({mode}) {status}",
            service=service,
            mode=mode,
            status=status,
        )


def check_required_services(
    config_root: Path, progress: ProgressReporter | None = None
) -> list[str]:
    """Check that required health services are active. Returns failed units."""
    health_path = config_root / "health-required.json"
    if not health_path.exists():
        return []
    try:
        required = json.loads(health_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(required, list) or not required:
        return []

    runtime_modes = _load_runtime_unit_modes(config_root)
    failed: list[str] = []
    for unit in required:
        service = f"{unit}.service"
        mode = runtime_modes.get(service, "rootful")
        if progress:
            progress.set_stage("health-check", f"checking {service} ({mode})")
        try:
            result = _check_service(service, mode)
            if result.returncode != 0:
                failed.append(service)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            failed.append(service)
    return failed


# --- Complete Reapply Orchestration ---


def complete_reapply(
    config_root: Path, progress: ProgressReporter | None = None
) -> tuple[bool, list[str], str]:
    """Run activation + health checks, rolling back on failure.

    Returns:
        (success, failures_list, rollback_status)
    """
    report_runtime_deploy_start(config_root, progress)
    activation_failures = activate_services(progress)
    if not activation_failures:
        report_runtime_services(config_root, progress)
    health_failures = [] if activation_failures else check_required_services(config_root, progress)
    failures = activation_failures + health_failures
    if failures:
        if progress:
            progress.set_stage("rollback", "restoring previous config")
        restored = restore_rollback(config_root)
        if restored:
            rollback_failures = activate_services(progress)
            if not rollback_failures:
                rollback_failures = check_required_services(config_root, progress)
            if rollback_failures:
                return (
                    False,
                    failures
                    + [
                        f"rollback activation/health failed: {failure}"
                        for failure in rollback_failures
                    ],
                    "failed",
                )
        return False, failures, "completed" if restored else "skipped"
    if progress:
        progress.set_stage("cleanup", "removing rollback state")
    cleanup_rollback(config_root)
    return True, [], "skipped"
