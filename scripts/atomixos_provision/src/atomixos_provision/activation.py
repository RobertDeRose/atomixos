"""Activation script runner, service health checks, and rollback."""

import json
import os
import pwd
import shutil
import subprocess
import time
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
DEFAULT_ACTIVATION_POLICY = {
    "required": [],
    "timeout_seconds": 300,
    "settle_seconds": 0,
    "restart": [],
    "allow_degraded": [],
    "strategy": "rollback",
}


class ActivationPolicyError(ValueError):
    """Raised when rendered activation policy is invalid at apply time."""


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


def load_activation_policy(config_root: Path) -> dict[str, object]:
    """Load activation policy, falling back to the legacy health-required file."""
    policy_path = config_root / "activation-policy.json"
    policy = dict(DEFAULT_ACTIVATION_POLICY)
    if policy_path.exists():
        try:
            raw_policy = json.loads(policy_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            raise ActivationPolicyError(f"invalid activation policy: {policy_path}") from exc
        if not isinstance(raw_policy, dict):
            raise ActivationPolicyError(f"activation policy must be an object: {policy_path}")
        policy.update(raw_policy)
        policy["strict_units"] = True
        validate_runtime_activation_policy(config_root, policy, strict_units=True)
        return policy

    health_path = config_root / "health-required.json"
    if health_path.exists():
        try:
            required = json.loads(health_path.read_text())
        except (json.JSONDecodeError, OSError):
            return policy
        if isinstance(required, list):
            policy["required"] = [unit for unit in required if isinstance(unit, str)]
    policy["strict_units"] = False
    validate_runtime_activation_policy(config_root, policy, strict_units=False)
    return policy


def validate_runtime_activation_policy(
    config_root: Path, policy: dict[str, object], *, strict_units: bool
) -> None:
    runtime_services = {unit.get("service", "") for unit in _load_runtime_units(config_root)}
    for key in ("required", "restart", "allow_degraded"):
        values = policy.get(key, [])
        if not isinstance(values, list):
            raise ActivationPolicyError(f"activation policy {key} must be a list")
        for value in values:
            if not isinstance(value, str):
                raise ActivationPolicyError(f"activation policy {key} entries must be strings")
            service = service_name(value)
            if strict_units and service not in runtime_services:
                raise ActivationPolicyError(
                    f"activation policy {key} references unknown provisioned service: {value}"
                )

    timeout_seconds = policy.get("timeout_seconds", BOOTSTRAP_ACTIVATION_TIMEOUT_SECONDS)
    settle_seconds = policy.get("settle_seconds", 0)
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool):
        raise ActivationPolicyError("activation policy timeout_seconds must be an integer")
    if not isinstance(settle_seconds, int) or isinstance(settle_seconds, bool):
        raise ActivationPolicyError("activation policy settle_seconds must be an integer")
    if not 1 <= timeout_seconds <= 3600:
        raise ActivationPolicyError("activation policy timeout_seconds must be in range 1..3600")
    if not 0 <= settle_seconds <= 300:
        raise ActivationPolicyError("activation policy settle_seconds must be in range 0..300")
    if policy.get("strategy", "rollback") != "rollback":
        raise ActivationPolicyError("activation policy strategy must be rollback")
    if "allow_degraded_configured" in policy and not isinstance(
        policy["allow_degraded_configured"], bool
    ):
        raise ActivationPolicyError(
            "activation policy allow_degraded_configured must be a boolean"
        )


def activate_services(
    progress: ProgressReporter | None = None,
    timeout_seconds: int = BOOTSTRAP_ACTIVATION_TIMEOUT_SECONDS,
) -> list[str]:
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
            timeout=timeout_seconds,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            return [f"activation script failed (exit {result.returncode}): {stderr[:200]}"]
    except subprocess.TimeoutExpired:
        return [f"activation script timed out after {timeout_seconds}s"]
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


def command_timeout(deadline: float | None) -> float:
    if deadline is None:
        return 10
    return max(0.001, min(10, remaining_timeout(deadline)))


def _check_rootless_service(
    service: str, deadline: float | None = None
) -> subprocess.CompletedProcess:
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
        timeout=command_timeout(deadline),
    )


def _check_service(
    service: str, mode: str, deadline: float | None = None
) -> subprocess.CompletedProcess:
    if mode == "rootless":
        return _check_rootless_service(service, deadline)
    return subprocess.run(
        ["systemctl", "is-active", "--quiet", service], timeout=command_timeout(deadline)
    )


def remaining_timeout(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def report_runtime_services(
    config_root: Path,
    progress: ProgressReporter | None = None,
    deadline: float | None = None,
) -> dict[str, str]:
    """Report status for every rendered runtime unit without failing the apply."""
    statuses: dict[str, str] = {}
    for unit in _load_runtime_units(config_root):
        service = unit.get("service", "")
        if not service:
            continue
        mode = unit.get("mode", "rootful")
        try:
            result = _check_service(service, mode, deadline)
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


def degraded_service_failures(
    policy: dict[str, object], statuses: dict[str, str]
) -> list[str]:
    """Return failed non-required services that are not explicitly allowed degraded."""
    if not policy.get("strict_units", False) or not policy.get(
        "allow_degraded_configured", False
    ):
        return []
    required = {service_name(unit) for unit in policy.get("required", []) if isinstance(unit, str)}
    allowed = {
        service_name(unit) for unit in policy.get("allow_degraded", []) if isinstance(unit, str)
    }
    return [
        service
        for service, status in statuses.items()
        if status != "running" and service not in required and service not in allowed
    ]


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


def service_name(unit: str) -> str:
    return unit if unit.endswith(".service") else f"{unit}.service"


def check_required_services(
    config_root: Path,
    progress: ProgressReporter | None = None,
    policy: dict[str, object] | None = None,
    deadline: float | None = None,
) -> list[str]:
    """Check that required health services are active. Returns failed units."""
    activation_policy = policy or load_activation_policy(config_root)
    required = activation_policy.get("required", [])
    if not isinstance(required, list) or not required:
        return []

    runtime_modes = _load_runtime_unit_modes(config_root)
    strict_units = bool(activation_policy.get("strict_units", False))
    failed: list[str] = []
    for unit in required:
        if deadline is not None and remaining_timeout(deadline) <= 0:
            failed.append("activation health checks timed out")
            break
        if not isinstance(unit, str):
            continue
        service = service_name(unit)
        if strict_units and service not in runtime_modes:
            failed.append(service)
            continue
        mode = runtime_modes.get(service, "rootful")
        if progress:
            progress.set_stage("health-check", f"checking {service} ({mode})")
        try:
            result = _check_service(service, mode, deadline)
            if result.returncode != 0:
                failed.append(service)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            failed.append(service)
    return failed


def restart_activation_services(
    config_root: Path,
    policy: dict[str, object],
    progress: ProgressReporter | None = None,
    deadline: float | None = None,
) -> list[str]:
    restart = policy.get("restart", [])
    if not isinstance(restart, list) or not restart:
        return []
    runtime_modes = _load_runtime_unit_modes(config_root)
    failures: list[str] = []
    for unit in restart:
        if deadline is not None and remaining_timeout(deadline) <= 0:
            failures.append("activation restart timed out")
            break
        if not isinstance(unit, str):
            continue
        service = service_name(unit)
        if service not in runtime_modes:
            failures.append(service)
            continue
        mode = runtime_modes[service]
        if progress:
            progress.set_stage("service-restart", f"restarting {service} ({mode})")
        try:
            result = _restart_service(service, mode, deadline)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            failures.append(service)
            continue
        if result.returncode != 0:
            failures.append(service)
    return failures


def _restart_service(
    service: str, mode: str, deadline: float | None = None
) -> subprocess.CompletedProcess:
    if mode == "rootless":
        return _restart_rootless_service(service, deadline)
    return subprocess.run(["systemctl", "restart", service], timeout=command_timeout(deadline))


def _restart_rootless_service(
    service: str, deadline: float | None = None
) -> subprocess.CompletedProcess:
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
            "restart",
            service,
        ],
        timeout=command_timeout(deadline),
    )


# --- Complete Reapply Orchestration ---


def run_activation_sequence(
    config_root: Path, progress: ProgressReporter | None = None
) -> list[str]:
    policy = load_activation_policy(config_root)
    timeout_seconds = int(policy.get("timeout_seconds", BOOTSTRAP_ACTIVATION_TIMEOUT_SECONDS))
    settle_seconds = int(policy.get("settle_seconds", 0))
    deadline = time.monotonic() + timeout_seconds

    report_runtime_deploy_start(config_root, progress)
    activation_failures = activate_services(progress, timeout_seconds)
    restart_failures = [] if activation_failures else restart_activation_services(
        config_root, policy, progress, deadline
    )
    if not restart_failures and not activation_failures and settle_seconds:
        if settle_seconds > remaining_timeout(deadline):
            return ["activation timed out before health checks"]
        if progress:
            progress.set_stage("settle", f"waiting {settle_seconds}s before health checks")
        time.sleep(settle_seconds)
    if not restart_failures and not activation_failures:
        statuses = report_runtime_services(config_root, progress, deadline)
        degraded_failures = degraded_service_failures(policy, statuses)
    else:
        degraded_failures = []
    health_failures = (
        []
        if restart_failures or activation_failures
        else check_required_services(config_root, progress, policy, deadline)
    )
    return activation_failures + restart_failures + degraded_failures + health_failures


def complete_reapply(
    config_root: Path, progress: ProgressReporter | None = None
) -> tuple[bool, list[str], str]:
    """Run activation + health checks, rolling back on failure.

    Returns:
        (success, failures_list, rollback_status)
    """
    try:
        failures = run_activation_sequence(config_root, progress)
    except ActivationPolicyError as exc:
        failures = [str(exc)]
    if failures:
        if progress:
            progress.set_stage("rollback", "restoring previous config")
        restored = restore_rollback(config_root)
        if restored:
            try:
                rollback_failures = run_activation_sequence(config_root, progress)
            except ActivationPolicyError as exc:
                rollback_failures = [str(exc)]
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
