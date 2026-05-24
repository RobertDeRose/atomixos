"""First-boot and re-apply provision orchestration."""

import asyncio
import contextlib
import fcntl
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Protocol

from atomixos_provision.activation import (
    BOOTSTRAP_ACTIVATION_ENV,
    atomic_promote,
    atomic_promote_initial,
    candidate_root_path,
    carry_forward_managed_state,
    cleanup_rollback,
    complete_reapply,
    discard_initial_config,
    recover_config_root,
)
from atomixos_provision.bundle import copy_bundle_files, prepare_source_bytes, prepare_source_path
from atomixos_provision.config import ProvisionError, load_config
from atomixos_provision.quadlet import (
    RUNTIME_METADATA_FILENAME,
    render_builds,
    render_containers,
    render_networks,
    render_volumes,
)

__all__ = [
    "apply_config_bytes",
    "import_config_from_path",
    "provisioning_lock",
    "validate_config_bytes",
    "validate_config_from_path",
    "validate_config_root",
]


class ProgressReporter(Protocol):
    def set_stage(
        self, name: str, detail: str | None = None, **fields: str | int | float | bool
    ) -> None: ...


# --- Constants ---

FIREWALL_INBOUND_FILENAME = "firewall-inbound.json"
LAN_SETTINGS_FILENAME = "lan-settings.json"
HOST_NETWORK_FILENAME = "host-network.json"
OS_UPGRADE_FILENAME = "os-upgrade.json"
HEALTH_REQUIRED_FILENAME = "health-required.json"
APP_RUNTIME_USER = "appsvc"
ROOTLESS_NETWORK_NAME = "pasta"


# --- State Writing ---


def validate_config_root(config_root: Path) -> Path:
    """Reject config roots that would make sibling promotion paths dangerous."""
    resolved = config_root.resolve(strict=False)
    if not resolved.is_absolute() or resolved.parent == resolved:
        raise ProvisionError(f"unsafe config root: {config_root}")
    if config_root.exists() and config_root.is_symlink():
        raise ProvisionError(f"config root must not be a symlink: {config_root}")
    if os.environ.get("ATOMIXOS_ALLOW_UNSAFE_CONFIG_ROOT") == "1":
        return resolved
    if resolved != Path("/data/config"):
        raise ProvisionError("config root must be /data/config")
    if resolved in (Path("/"), Path("/data")):
        raise ProvisionError(f"unsafe config root: {resolved}")
    if resolved.parent == Path("/data") and resolved != Path("/data/config"):
        raise ProvisionError(f"unsafe config root parent: {resolved.parent}")
    return resolved


@contextlib.contextmanager
def provisioning_lock(config_root: Path):
    """Serialize config-root mutations across API, CLI, and service processes."""
    config_root.parent.mkdir(parents=True, exist_ok=True)
    lock_path = config_root.parent / f".{config_root.name}.lock"
    with lock_path.open("w") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def write_imported_state(
    parsed: dict[str, Any],
    config_path: Path,
    files_path: Path | None,
    config_root: Path,
    runtime_config_root: Path | None = None,
) -> list[str]:
    """Write all parsed config state to the config root directory.

    Returns a list of non-fatal warnings from container rendering.
    """
    config_root.mkdir(parents=True, exist_ok=True)
    render_root = runtime_config_root or config_root
    (config_root / "ssh-authorized-keys").mkdir(parents=True, exist_ok=True)

    # Copy config.toml
    shutil.copyfile(config_path, config_root / "config.toml")
    (config_root / "config.toml").chmod(0o600)

    # Copy bundle files
    copy_bundle_files(files_path, config_root)

    # Write admin SSH keys for auth
    ssh_keys = parsed.get("ssh_keys", [])
    if ssh_keys:
        admin_signers = config_root / "admin-signers"
        admin_signers.write_text("\n".join(ssh_keys) + "\n")
        admin_signers.chmod(0o600)

    # Write user state consumed by atomixos-apply-users.service
    users = parsed.get("users", {})
    users_path = config_root / "users.json"
    users_path.write_text(json.dumps(users, indent=2) + "\n")
    users_path.chmod(0o600)

    ssh_dir = config_root / "ssh-authorized-keys"
    desired_key_files = set(users)
    for existing_key_file in ssh_dir.iterdir():
        if existing_key_file.is_file() and existing_key_file.name not in desired_key_files:
            existing_key_file.unlink()

    for username, user in users.items():
        user_ssh_path = ssh_dir / username
        ssh_key = user.get("ssh_key", "")
        if ssh_key:
            user_ssh_path.write_text(ssh_key + "\n")
            user_ssh_path.chmod(0o600)
        else:
            user_ssh_path.unlink(missing_ok=True)

    # Write firewall inbound rules
    firewall = parsed.get("firewall_inbound", {})
    firewall_path = config_root / FIREWALL_INBOUND_FILENAME
    firewall_path.write_text(json.dumps(firewall, indent=2) + "\n")
    firewall_path.chmod(0o600)

    # Write LAN settings
    lan_settings = parsed.get("lan_settings", {})
    lan_path = config_root / LAN_SETTINGS_FILENAME
    lan_path.write_text(json.dumps(lan_settings, indent=2) + "\n")
    lan_path.chmod(0o600)

    # Write host network settings consumed by lan-gateway-apply.service
    host_network = parsed.get("host_network", {})
    host_network_path = config_root / HOST_NETWORK_FILENAME
    host_network_path.write_text(json.dumps(host_network, indent=2) + "\n")
    host_network_path.chmod(0o600)

    # Write OS upgrade settings
    os_upgrade = parsed.get("os_upgrade")
    os_path = config_root / OS_UPGRADE_FILENAME
    if os_upgrade:
        os_path.write_text(json.dumps(os_upgrade, indent=2) + "\n")
        os_path.chmod(0o600)
    elif os_path.exists():
        os_path.unlink()

    # Write health-required.json
    required_units = parsed.get("required_units", [])
    health_path = config_root / HEALTH_REQUIRED_FILENAME
    health_path.write_text(json.dumps(required_units, indent=2) + "\n")
    health_path.chmod(0o600)

    # Render and write Quadlet units
    containers = parsed.get("containers", {})
    rendered_units: dict[str, str] = {}
    runtime_units: list[dict[str, str]] = []
    warnings: list[str] = []

    container_table = containers.get("container", {})
    if container_table:
        r, ru, w = render_containers(container_table, render_root)
        rendered_units.update(r)
        runtime_units.extend(ru)
        warnings.extend(w)

    network_table = containers.get("network")
    if network_table:
        r, ru = render_networks(network_table, render_root)
        rendered_units.update(r)
        runtime_units.extend(ru)

    volume_table = containers.get("volume")
    if volume_table:
        r, ru = render_volumes(
            volume_table, render_root, infer_volume_modes(container_table, volume_table)
        )
        rendered_units.update(r)
        runtime_units.extend(ru)

    build_table = containers.get("build")
    if build_table:
        r, ru = render_builds(
            build_table, render_root, infer_build_modes(container_table, build_table)
        )
        rendered_units.update(r)
        runtime_units.extend(ru)

    validate_unique_runtime_services(runtime_units)

    # Write Quadlet unit files
    quadlet_dir = config_root / "quadlet"
    quadlet_dir.mkdir(parents=True, exist_ok=True)
    for existing in quadlet_dir.iterdir():
        if existing.is_file():
            existing.unlink()
    for filename, content in rendered_units.items():
        unit_path = quadlet_dir / filename
        unit_path.write_text(content)
        unit_path.chmod(0o644)

    # Write runtime metadata
    runtime_metadata = {
        "app_user": APP_RUNTIME_USER,
        "rootless_network": ROOTLESS_NETWORK_NAME,
        "units": runtime_units,
    }
    metadata_path = config_root / RUNTIME_METADATA_FILENAME
    metadata_path.write_text(json.dumps(runtime_metadata, indent=2) + "\n")
    metadata_path.chmod(0o600)

    # Return warnings instead of mutating the input dict
    return warnings


def infer_build_modes(container_table: dict, build_table: dict | None) -> dict[str, set[str]]:
    """Infer build unit mode from rootless containers consuming each ImageTag."""
    if not build_table:
        return {}

    rootful_images: set[str] = set()
    rootless_images: set[str] = set()
    for raw_sections in container_table.values():
        container = raw_sections.get("Container")
        if not isinstance(container, dict):
            continue
        image = container.get("Image")
        if isinstance(image, list):
            image = image[0] if image else None
        if isinstance(image, str):
            target = rootful_images if raw_sections.get("privileged") is True else rootless_images
            target.add(image.strip())

    build_modes: dict[str, set[str]] = {}
    for build_name, raw_sections in build_table.items():
        build = raw_sections.get("Build") if isinstance(raw_sections, dict) else None
        if not isinstance(build, dict):
            continue
        image_tag = build.get("ImageTag")
        if isinstance(image_tag, list):
            image_tag = image_tag[0] if image_tag else None
        if not isinstance(image_tag, str):
            continue
        tag = image_tag.strip()
        modes: set[str] = set()
        if tag in rootful_images:
            modes.add("rootful")
        if tag in rootless_images:
            modes.add("rootless")
        if modes:
            build_modes[build_name] = modes
    return build_modes


def infer_volume_modes(container_table: dict, volume_table: dict | None) -> dict[str, set[str]]:
    """Infer volume unit modes from containers consuming named volumes."""
    if not volume_table:
        return {}

    volume_names = set(volume_table)
    volume_modes: dict[str, set[str]] = {name: set() for name in volume_names}
    for raw_sections in container_table.values():
        container = raw_sections.get("Container")
        if not isinstance(container, dict):
            continue
        values = container.get("Volume", [])
        if not isinstance(values, list):
            values = [values]
        mode = "rootful" if raw_sections.get("privileged") is True else "rootless"
        for value in values:
            if not isinstance(value, str) or ":" not in value:
                continue
            source = value.split(":", 1)[0]
            if source in volume_names:
                volume_modes[source].add(mode)
    return {name: modes for name, modes in volume_modes.items() if modes}


def validate_unique_runtime_services(runtime_units: list[dict[str, str]]) -> None:
    """Reject configs that render multiple Quadlets to the same systemd service."""
    seen: dict[tuple[str, str], str] = {}
    for unit in runtime_units:
        service = unit["service"]
        mode = unit["mode"]
        filename = unit["filename"]
        previous = seen.get((mode, service))
        if previous is not None:
            message = (
                "quadlet service name collision: "
                f"{previous} and {filename} both render {service} ({mode})"
            )
            raise ProvisionError(message)
        seen[(mode, service)] = filename


def provisioning_forwarding_url(parsed: dict[str, Any]) -> str | None:
    lan_settings = parsed.get("lan_settings")
    if not isinstance(lan_settings, dict):
        return None
    gateway_ip = lan_settings.get("gateway_ip")
    if not isinstance(gateway_ip, str) or not gateway_ip:
        return None
    return f"http://{gateway_ip}:8080"


def schedule_bootstrap_rebind(parsed: dict[str, Any]) -> None:
    """Restart bootstrap socket after apply has completed."""
    if provisioning_forwarding_url(parsed) is None:
        return
    try:
        subprocess.run(
            [
                "systemd-run",
                "--unit=atomixos-bootstrap-rebind-delayed",
                "--on-active=30s",
                "--property=Type=oneshot",
                "/bin/sh",
                "-c",
                "systemctl restart bootstrap-wan-toggle.service || true; "
                "systemctl daemon-reload && "
                "systemctl restart atomixos-bootstrap-rebind.service && "
                "systemctl stop atomixos-bootstrap.service && "
                "systemctl restart atomixos-bootstrap.socket && "
                "systemctl start atomixos-bootstrap.service",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return


def reconcile_bootstrap_wan() -> None:
    """Best-effort reconciliation of first-boot WAN bootstrap firewall state."""
    try:
        subprocess.run(
            ["systemctl", "restart", "bootstrap-wan-toggle.service"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return


# --- Orchestration ---


def _provision_prepared_sync(
    config_path: Path,
    files_path: Path | None,
    config_root: Path,
    progress: ProgressReporter | None = None,
    allow_reapply: bool = True,
) -> dict[str, Any]:
    """Apply a prepared config source using the shared promotion flow."""
    config_root = validate_config_root(config_root)
    if progress:
        progress.set_stage("recover", "checking for interrupted promotion")
    recover_config_root(config_root)
    is_reapply = (config_root / "config.toml").exists()
    if is_reapply and not allow_reapply:
        message = "config already provisioned; reapply requires authenticated API access"
        raise ProvisionError(message)

    if not is_reapply:
        if progress:
            progress.set_stage("validate", "parsing config")
        candidate_root = candidate_root_path(config_root)
        if candidate_root.exists():
            shutil.rmtree(candidate_root)
        candidate_root.mkdir(parents=True, exist_ok=True)
        try:
            parsed = load_config(config_path)
            if progress:
                progress.set_stage("write-candidate", "rendering provisioned state")
            warnings = write_imported_state(
                parsed, config_path, files_path, candidate_root, config_root
            )
        except Exception:
            shutil.rmtree(candidate_root, ignore_errors=True)
            raise
        if progress:
            progress.set_stage("promote", "activating initial config root")
        atomic_promote_initial(config_root, candidate_root)
        if os.environ.get(BOOTSTRAP_ACTIVATION_ENV):
            success, failures, rollback_status = complete_reapply(config_root, progress)
            if not success:
                error_msg = f"activation failed: {', '.join(failures)}"
                exc = ProvisionError(error_msg)
                if rollback_status == "completed":
                    exc.rollback_status = "completed"  # type: ignore[attr-defined]
                else:
                    discard_initial_config(config_root)
                    reconcile_bootstrap_wan()
                    exc.rollback_status = "discarded"  # type: ignore[attr-defined]
                raise exc
        elif os.environ.get("ATOMIXOS_KEEP_INITIAL_PROMOTION_PENDING") != "1":
            cleanup_rollback(config_root)
        reconcile_bootstrap_wan()
        if progress:
            progress.set_stage("complete", "initial provisioning complete")
        return {
            "warnings": warnings,
            "reapply": False,
            "forwarding_url": provisioning_forwarding_url(parsed),
        }

    # Re-apply: render into candidate, promote atomically
    if progress:
        progress.set_stage("validate", "parsing config")
    candidate_root = candidate_root_path(config_root)
    if candidate_root.exists():
        shutil.rmtree(candidate_root)
    candidate_root.mkdir(parents=True, exist_ok=True)

    try:
        parsed = load_config(config_path)
        if progress:
            progress.set_stage("write-candidate", "rendering provisioned state")
        warnings = write_imported_state(
            parsed, config_path, files_path, candidate_root, config_root
        )
        carry_forward_managed_state(config_root, candidate_root)
    except Exception:
        shutil.rmtree(candidate_root, ignore_errors=True)
        raise

    # Atomic promotion
    if progress:
        progress.set_stage("promote", "swapping active config root")
    atomic_promote(config_root, candidate_root)

    # Run activation and health checks
    success, failures, rollback_status = complete_reapply(config_root, progress)

    if not success:
        error_msg = f"activation failed: {', '.join(failures)}"
        exc = ProvisionError(error_msg)
        exc.rollback_status = rollback_status  # type: ignore[attr-defined]
        raise exc

    schedule_bootstrap_rebind(parsed)
    return {
        "warnings": warnings,
        "reapply": True,
        "rolled_back": False,
        "forwarding_url": provisioning_forwarding_url(parsed),
    }


def _provision_sync(
    payload: bytes,
    filename: str,
    config_root: Path,
    progress: ProgressReporter | None = None,
    allow_reapply: bool = True,
) -> dict[str, Any]:
    """Synchronous provision logic (runs in thread for async wrapper)."""
    if progress:
        progress.set_stage("prepare", f"unpacking {filename}")
    tmpdir, config_path, files_path = prepare_source_bytes(payload, filename)
    try:
        with provisioning_lock(config_root):
            return _provision_prepared_sync(
                config_path, files_path, config_root, progress, allow_reapply
            )
    finally:
        tmpdir.cleanup()


def _validate_sync(payload: bytes, filename: str, config_root: Path) -> dict[str, Any]:
    """Synchronous validation (no state changes)."""
    tmpdir, config_path, _files_path = prepare_source_bytes(payload, filename)
    try:
        parsed = load_config(config_path)
        with tempfile.TemporaryDirectory() as validation_dir:
            validation_root = Path(validation_dir) / "config"
            warnings = write_imported_state(
                parsed, config_path, None, validation_root, config_root
            )
        return {"warnings": warnings}
    finally:
        tmpdir.cleanup()


def import_config_from_path(source_path: Path, config_root: Path) -> dict[str, Any]:
    """Import a config from a file path using crash-safe atomic promotion.

    Reuses the same candidate-root + promote/rollback path as the web server.
    Used by the CLI import command and first-boot.sh.
    """
    config_root = validate_config_root(config_root)
    tmpdir, config_path, files_path = prepare_source_path(source_path)
    try:
        with provisioning_lock(config_root):
            return _provision_prepared_sync(config_path, files_path, config_root)
    finally:
        if tmpdir is not None:
            tmpdir.cleanup()


def validate_config_from_path(
    source_path: Path, config_root: Path | None = None
) -> dict[str, Any]:
    """Validate a config source path without applying it."""
    tmpdir, config_path, _files_path = prepare_source_path(source_path)
    try:
        return _validate_sync(
            config_path.read_bytes(), config_path.name, config_root or Path("/data/config")
        )
    finally:
        if tmpdir is not None:
            tmpdir.cleanup()


# --- Async Wrappers ---


async def apply_config_bytes(
    payload: bytes,
    filename: str,
    config_root: Path,
    progress: ProgressReporter | None = None,
    allow_reapply: bool = True,
) -> dict[str, Any]:
    """Apply config bytes in a thread (used by both API jobs and UI forms)."""
    return await asyncio.to_thread(
        _provision_sync, payload, filename, config_root, progress, allow_reapply
    )


async def validate_config_bytes(
    payload: bytes, filename: str, config_root: Path
) -> dict[str, Any]:
    """Validate config bytes without applying."""
    return await asyncio.to_thread(_validate_sync, payload, filename, config_root)
