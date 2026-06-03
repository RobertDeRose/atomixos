"""First-boot and re-apply provision orchestration."""

import asyncio
import contextlib
import errno
import fcntl
import grp
import json
import os
import pwd
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
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
from atomixos_provision.bundle import (
    copy_bundle_files,
    prepare_source_bytes,
    prepare_source_path,
    stage_bundle_files,
)
from atomixos_provision.config import ProvisionError, load_config
from atomixos_provision.quadlet import (
    RUNTIME_METADATA_FILENAME,
    render_builds,
    render_containers,
    render_networks,
    render_volumes,
)
from atomixos_provision.staging import (
    MANIFEST_VERSION,
    ClaimedJob,
    RuntimePaths,
    claim_next_job,
    cleanup_claimed_job,
    ensure_runtime_layout,
    finalize_abandoned_active_jobs,
    has_staged_jobs,
    publish_ready_marker,
    read_json,
    read_result,
    runtime_paths,
    sha256_file,
    staged_job_presence,
    tree_manifest,
    try_abandon_queued_job,
    validate_job_id,
    validate_relative_path,
    verify_staged_job,
    write_json_atomic,
    write_result,
)

__all__ = [
    "apply_config_bytes",
    "apply_config_operation",
    "apply_config_transform",
    "apply_staged_job",
    "finalize_staged_jobs",
    "import_config_from_path",
    "locked_export_config_bytes",
    "provisioning_lock",
    "stage_config_bytes",
    "stage_config_operation",
    "validate_config_bytes",
    "validate_config_from_path",
    "validate_config_root",
]


class ProgressReporter(Protocol):
    def set_stage(
        self, name: str, detail: str | None = None, **fields: str | int | float | bool
    ) -> None: ...


class StagedQueueBusyError(ProvisionError):
    """Raised when an operation requires the staged queue to be empty."""


# --- Constants ---

FIREWALL_INBOUND_FILENAME = "firewall-inbound.json"
LAN_SETTINGS_FILENAME = "lan-settings.json"
HOST_NETWORK_FILENAME = "host-network.json"
ACTIVATION_POLICY_FILENAME = "activation-policy.json"
OS_UPGRADE_FILENAME = "os-upgrade.json"
HEALTH_REQUIRED_FILENAME = "health-required.json"
APP_RUNTIME_USER = "appsvc"
ROOTLESS_NETWORK_NAME = "pasta"
PROVISION_SERVICE_USER = "atomixos-provision"
PROVISION_SERVICE_GROUP = "atomixos-provision"
PROVISION_LOCK_DIR = Path("/run/atomixos-provision")
PROVISION_RUNTIME_DIR_ENV = "ATOMIXOS_PROVISION_RUNTIME_DIR"
PROVISION_WORKER_ACTIVE_ENV = "ATOMIXOS_PROVISION_WORKER_ACTIVE"
FIRST_CONFIG_MARKER = ".first-config"
STAGED_RESULT_TIMEOUT_SECONDS = int(
    os.environ.get("ATOMIXOS_PROVISION_RESULT_TIMEOUT_SECONDS", "1200")
)


# --- State Writing ---


def validate_config_root(config_root: Path, *, allow_unsafe_env: bool = True) -> Path:
    """Reject config roots that would make sibling promotion paths dangerous."""
    resolved = config_root.resolve(strict=False)
    if not resolved.is_absolute() or resolved.parent == resolved:
        raise ProvisionError(f"unsafe config root: {config_root}")
    if config_root.exists() and config_root.is_symlink():
        raise ProvisionError(f"config root must not be a symlink: {config_root}")
    if allow_unsafe_env and os.environ.get("ATOMIXOS_ALLOW_UNSAFE_CONFIG_ROOT") == "1":
        return resolved
    if resolved != Path("/data/config"):
        raise ProvisionError("config root must be /data/config")
    if resolved in (Path("/"), Path("/data")):
        raise ProvisionError(f"unsafe config root: {resolved}")
    if resolved.parent == Path("/data") and resolved != Path("/data/config"):
        raise ProvisionError(f"unsafe config root parent: {resolved.parent}")
    return resolved


def staging_enabled() -> bool:
    return not os.environ.get(PROVISION_WORKER_ACTIVE_ENV)


def require_worker_for_data_config(config_root: Path, operation: str) -> None:
    if config_root.resolve(strict=False) == Path("/data/config") and staging_enabled():
        raise ProvisionError(f"{operation} for /data/config requires privileged worker context")


def _runtime_paths() -> RuntimePaths:
    return runtime_paths(Path(os.environ.get(PROVISION_RUNTIME_DIR_ENV, PROVISION_LOCK_DIR)))


def _service_identity() -> tuple[int, int] | None:
    try:
        return (
            pwd.getpwnam(PROVISION_SERVICE_USER).pw_uid,
            grp.getgrnam(PROVISION_SERVICE_GROUP).gr_gid,
        )
    except KeyError:
        return None


def _first_config_marker_path(config_root: Path) -> Path:
    return config_root / FIRST_CONFIG_MARKER


def _has_first_config_marker(config_root: Path) -> bool:
    return _first_config_marker_path(config_root).is_file()


def _write_first_config_marker(candidate_root: Path) -> None:
    marker = _first_config_marker_path(candidate_root)
    marker.write_text("ok\n", encoding="utf-8")
    marker.chmod(0o600)


def _grant_service_read_access(config_root: Path) -> None:
    identity = _service_identity()
    if identity is None:
        return
    _uid, gid = identity
    files_root = config_root / "files"
    for path in [config_root, *config_root.rglob("*")]:
        if path == files_root or files_root in path.parents:
            continue
        try:
            path_stat = path.lstat()
            if stat.S_ISLNK(path_stat.st_mode):
                raise ProvisionError(f"config state must not contain symlink: {path}")
            os.chown(path, -1, gid, follow_symlinks=False)
            current_mode = stat.S_IMODE(path_stat.st_mode)
            if stat.S_ISDIR(path_stat.st_mode):
                path.chmod(current_mode | stat.S_IRGRP | stat.S_IXGRP)
            else:
                path.chmod(current_mode | stat.S_IRGRP)
        except FileNotFoundError:
            continue


@contextlib.contextmanager
def provisioning_lock(config_root: Path):
    """Serialize config-root mutations across API, CLI, and service processes."""
    lock_path = _provisioning_lock_path(config_root)
    with _open_lock_file(lock_path) as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _provisioning_lock_path(config_root: Path) -> Path:
    resolved = config_root.resolve(strict=False)
    if resolved == Path("/data/config"):
        return PROVISION_LOCK_DIR / "config.lock"
    return resolved.parent / f".{resolved.name}.lock"


def _open_lock_file(lock_path: Path):
    if lock_path.parent != PROVISION_LOCK_DIR:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        return lock_path.open("a+")

    _ensure_runtime_lock_parent(lock_path.parent)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(lock_path, flags, 0o660)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ProvisionError(f"lock file must not be a symlink: {lock_path}") from exc
        raise
    try:
        lock_stat = os.fstat(fd)
        if not stat.S_ISREG(lock_stat.st_mode):
            raise ProvisionError(f"lock path must be a regular file: {lock_path}")
        if os.geteuid() == 0:
            _ensure_runtime_lock_permissions(fd)
            lock_stat = os.fstat(fd)
        if _runtime_lock_requires_root_owner(lock_path.parent) and lock_stat.st_uid != 0:
            raise ProvisionError(f"lock file must be root-owned: {lock_path}")
        return os.fdopen(fd, "r+")
    except Exception:
        os.close(fd)
        raise


def _ensure_runtime_lock_parent(lock_dir: Path) -> None:
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_dir_stat = lock_dir.lstat()
    if stat.S_ISLNK(lock_dir_stat.st_mode) or not stat.S_ISDIR(lock_dir_stat.st_mode):
        raise ProvisionError(f"lock directory must be a directory: {lock_dir}")
    if _runtime_lock_requires_root_owner(lock_dir) and lock_dir_stat.st_uid != 0:
        raise ProvisionError(f"lock directory must be root-owned: {lock_dir}")
    if lock_dir_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ProvisionError(f"lock directory must not be group/world writable: {lock_dir}")


def _runtime_lock_requires_root_owner(lock_dir: Path) -> bool:
    return os.geteuid() == 0 or lock_dir == Path("/run/atomixos-provision")


def _ensure_runtime_lock_permissions(fd: int) -> None:
    identity = _service_identity()
    uid = 0
    gid = -1
    mode = 0o600
    if identity is not None:
        _uid, gid = identity
        mode = 0o660
    os.fchown(fd, uid, gid)
    os.fchmod(fd, mode)


def _manifest_service_identity() -> tuple[int, int]:
    identity = _service_identity()
    if identity is not None:
        return identity
    return os.geteuid(), os.getegid()


def _operation_type_for_manifest(is_reapply: bool, *, operation: str) -> str:
    if operation != "full-apply":
        return operation
    return "re-apply" if is_reapply else "initial-apply"


def _manifest_for_staged_candidate(
    *,
    job_id: str,
    config_path: Path,
    candidate_root: Path,
    bundle_root: Path,
    parsed: dict[str, Any],
    warnings: list[str],
    filename: str,
    source_digest: str | None,
    allow_reapply: bool,
    operation: str,
    is_reapply: bool,
    preserve_bundle_files: bool,
) -> dict[str, Any]:
    service_uid, service_gid = _manifest_service_identity()
    return {
        "version": MANIFEST_VERSION,
        "job_id": job_id,
        "operation": _operation_type_for_manifest(is_reapply, operation=operation),
        "source_filename": filename,
        "source_sha256": source_digest or sha256_file(config_path),
        "candidate": tree_manifest(candidate_root),
        "bundle_files": tree_manifest(bundle_root),
        "bundle_files_present": bundle_root.exists(),
        "preserve_bundle_files": preserve_bundle_files,
        "activation_policy": parsed.get(
            "activation_policy", {"required": parsed.get("required_units", [])}
        ),
        "allow_reapply": allow_reapply,
        "service_uid": service_uid,
        "service_gid": service_gid,
        "created_at": time.time(),
        "warnings": warnings,
        "lan_settings": parsed.get("lan_settings", {}),
        "forwarding_url": provisioning_forwarding_url(parsed),
    }


def _progress_job_id(progress: ProgressReporter | None) -> str:
    job_id = getattr(progress, "id", None)
    return str(job_id) if isinstance(job_id, str) and job_id else str(uuid.uuid4())


def _copy_current_bundle_files(config_root: Path, destination: Path) -> None:
    files_root = config_root / "files"
    if not files_root.exists():
        return
    stage_bundle_files(files_root, destination)


def _stage_prepared_sync(
    job_id: str,
    config_path: Path,
    files_path: Path | None,
    config_root: Path,
    *,
    filename: str,
    source_digest: str | None = None,
    allow_reapply: bool = True,
    operation: str = "full-apply",
    progress: ProgressReporter | None = None,
    wait_for_result: bool = True,
) -> dict[str, Any]:
    job_id = validate_job_id(job_id)
    config_root = validate_config_root(config_root)
    paths = _runtime_paths()
    ensure_runtime_layout(paths)
    is_reapply = _has_first_config_marker(config_root)
    if is_reapply and not allow_reapply:
        message = "config already provisioned; reapply requires authenticated API access"
        raise ProvisionError(message)

    job_path = paths.queue / job_id
    if job_path.exists() or (paths.queue / f"{job_id}.ready").exists():
        raise ProvisionError(f"staged job already exists: {job_id}")
    staging_path = paths.queue / f".{job_id}.staging.{os.getpid()}"
    if staging_path.exists():
        shutil.rmtree(staging_path)

    if progress:
        progress.set_stage("validate", "parsing config")
    parsed = load_config(config_path)
    candidate_root = staging_path / "candidate"
    bundle_root = staging_path / "bundle-files"
    try:
        staging_path.mkdir(parents=True, mode=0o700)
        if progress:
            progress.set_stage("write-candidate", "rendering provisioned state")
        warnings = write_imported_state(
            parsed, config_path, None, candidate_root, config_root, progress
        )
        if is_reapply:
            carry_forward_managed_state(config_root, candidate_root)
        preserve_bundle_files = False
        if files_path is not None:
            if progress:
                progress.set_stage("copy-files", "staging bundled files")
            stage_bundle_files(files_path, bundle_root)
        elif operation != "full-apply" and is_reapply and (config_root / "files").exists():
            preserve_bundle_files = True

        manifest = _manifest_for_staged_candidate(
            job_id=job_id,
            config_path=config_path,
            candidate_root=candidate_root,
            bundle_root=bundle_root,
            parsed=parsed,
            warnings=warnings,
            filename=filename,
            source_digest=source_digest,
            allow_reapply=allow_reapply,
            operation=operation,
            is_reapply=is_reapply,
            preserve_bundle_files=preserve_bundle_files,
        )
        write_json_atomic(staging_path / "manifest.json", manifest)
        os.replace(staging_path, job_path)
        publish_ready_marker(paths, job_id)
        (paths.queue / f"{job_id}.reserve").unlink(missing_ok=True)
        if progress:
            progress.set_stage("queued", "waiting for privileged apply worker")
        if not wait_for_result:
            return {"job_id": job_id, "queued": True}
        return _wait_for_staged_result(paths, job_id, progress)
    except Exception:
        shutil.rmtree(staging_path, ignore_errors=True)
        shutil.rmtree(job_path, ignore_errors=True)
        (paths.queue / f"{job_id}.ready").unlink(missing_ok=True)
        (paths.queue / f"{job_id}.reserve").unlink(missing_ok=True)
        raise


def stage_config_bytes(
    job_id: str,
    payload: bytes,
    filename: str,
    config_root: Path,
    *,
    allow_reapply: bool = True,
    progress: ProgressReporter | None = None,
) -> None:
    if progress:
        progress.set_stage("prepare", f"unpacking {filename}")
    tmpdir, config_path, files_path = prepare_source_bytes(payload, filename)
    try:
        _stage_prepared_sync(
            job_id,
            config_path,
            files_path,
            config_root,
            filename=filename,
            source_digest=sha256_file(config_path),
            allow_reapply=allow_reapply,
            progress=progress,
            wait_for_result=False,
        )
    finally:
        tmpdir.cleanup()


def _wait_for_staged_result(
    paths: RuntimePaths, job_id: str, progress: ProgressReporter | None = None
) -> dict[str, Any]:
    deadline = time.monotonic() + STAGED_RESULT_TIMEOUT_SECONDS
    last_stage = None
    while True:
        while time.monotonic() < deadline:
            result = read_result(paths, job_id)
            if result is not None:
                return _staged_result_payload_or_raise(result)
            marker_stage = "running" if (paths.active / job_id).exists() else "queued"
            if progress and marker_stage != last_stage:
                detail = (
                    "privileged apply worker is running"
                    if marker_stage == "running"
                    else "waiting for privileged apply worker"
                )
                progress.set_stage(marker_stage, detail)
                last_stage = marker_stage
            time.sleep(0.2)
        result = read_result(paths, job_id)
        if result is not None:
            return _staged_result_payload_or_raise(result)
        if not (paths.active / job_id).exists() and try_abandon_queued_job(paths, job_id):
            raise ProvisionError("timed out waiting for privileged apply worker")
        if staged_job_presence(paths, job_id) == "missing":
            raise ProvisionError("privileged apply worker did not publish a result")
        deadline = time.monotonic() + STAGED_RESULT_TIMEOUT_SECONDS


def _staged_result_payload_or_raise(result: dict[str, Any]) -> dict[str, Any]:
    status = result.get("status")
    if status == "succeeded":
        payload = result.get("result")
        if not isinstance(payload, dict):
            raise ProvisionError("staged apply result missing result payload")
        return payload
    message = result.get("error") if isinstance(result.get("error"), str) else "failed"
    error = ProvisionError(message)
    rollback_status = result.get("rollback_status")
    if isinstance(rollback_status, str):
        error.rollback_status = rollback_status  # type: ignore[attr-defined]
    raise error


def _stage_config_operation_sync(
    job_id: str,
    operation: dict[str, Any],
    config_root: Path,
    progress: ProgressReporter | None = None,
) -> None:
    config_root = validate_config_root(config_root)
    recover_config_root(config_root)
    paths = _runtime_paths()
    if has_staged_jobs(paths, exclude_job_id=job_id):
        raise StagedQueueBusyError("partial config updates require an empty staged queue")
    from atomixos_provision.partial_config import (
        apply_operation,
        canonical_config_bytes,
        load_current_config,
    )

    current = load_current_config(config_root)
    candidate = canonical_config_bytes(apply_operation(current, operation))
    tmpdir, config_path, _files_path = prepare_source_bytes(candidate, "config.toml")
    try:
        _stage_prepared_sync(
            job_id,
            config_path,
            None,
            config_root,
            filename="config.toml",
            source_digest=sha256_file(config_path),
            allow_reapply=True,
            operation="partial-apply",
            progress=progress,
            wait_for_result=False,
        )
    finally:
        tmpdir.cleanup()


def write_imported_state(
    parsed: dict[str, Any],
    config_path: Path,
    files_path: Path | None,
    config_root: Path,
    runtime_config_root: Path | None = None,
    progress: ProgressReporter | None = None,
) -> list[str]:
    """Write all parsed config state to the config root directory.

    Returns a list of non-fatal warnings from container rendering.
    """
    config_root.mkdir(parents=True, exist_ok=True)
    render_root = runtime_config_root or config_root
    (config_root / "ssh-authorized-keys").mkdir(parents=True, exist_ok=True)

    if progress:
        progress.set_stage("write-config", "writing config.toml")
    shutil.copyfile(config_path, config_root / "config.toml")
    (config_root / "config.toml").chmod(0o600)

    if progress and files_path is not None:
        progress.set_stage("copy-files", "copying bundled files")
    copy_bundle_files(files_path, config_root)

    if progress:
        progress.set_stage("write-admin-signers", "writing admin signer keys")
    ssh_keys = parsed.get("ssh_keys", [])
    if ssh_keys:
        admin_signers = config_root / "admin-signers"
        admin_signers.write_text("\n".join(ssh_keys) + "\n")
        admin_signers.chmod(0o600)

    if progress:
        progress.set_stage("write-users", "rendering user accounts")
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

    if progress:
        progress.set_stage("write-firewall", "rendering firewall rules")
    firewall = parsed.get("firewall_inbound", {})
    firewall_path = config_root / FIREWALL_INBOUND_FILENAME
    firewall_path.write_text(json.dumps(firewall, indent=2) + "\n")
    firewall_path.chmod(0o600)

    if progress:
        progress.set_stage("write-lan", "rendering LAN settings")
    lan_settings = parsed.get("lan_settings", {})
    lan_path = config_root / LAN_SETTINGS_FILENAME
    lan_path.write_text(json.dumps(lan_settings, indent=2) + "\n")
    lan_path.chmod(0o600)

    if progress:
        progress.set_stage("write-network", "rendering host network settings")
    host_network = parsed.get("host_network", {})
    host_network_path = config_root / HOST_NETWORK_FILENAME
    host_network_path.write_text(json.dumps(host_network, indent=2) + "\n")
    host_network_path.chmod(0o600)

    if progress:
        progress.set_stage("write-os-upgrade", "rendering OS upgrade settings")
    os_upgrade = parsed.get("os_upgrade")
    os_path = config_root / OS_UPGRADE_FILENAME
    if os_upgrade:
        os_path.write_text(json.dumps(os_upgrade, indent=2) + "\n")
        os_path.chmod(0o600)
    elif os_path.exists():
        os_path.unlink()

    if progress:
        progress.set_stage("write-health", "rendering health checks")
    required_units = parsed.get("required_units", [])
    health_path = config_root / HEALTH_REQUIRED_FILENAME
    health_path.write_text(json.dumps(required_units, indent=2) + "\n")
    health_path.chmod(0o600)

    # Write activation policy consumed by the re-apply activation path.
    activation_policy = parsed.get("activation_policy", {"required": required_units})
    activation_path = config_root / ACTIVATION_POLICY_FILENAME
    activation_path.write_text(json.dumps(activation_policy, indent=2) + "\n")
    activation_path.chmod(0o600)

    if progress:
        progress.set_stage("render-containers", "rendering container units")
    containers = parsed.get("containers", {})
    rendered_units: dict[str, str] = {}
    runtime_units: list[dict[str, str]] = []
    warnings: list[str] = []

    container_table = containers.get("container", {})
    if container_table:
        if progress:
            progress.set_stage("render-containers", "rendering containers")
        r, ru, w = render_containers(container_table, render_root)
        rendered_units.update(r)
        runtime_units.extend(ru)
        warnings.extend(w)

    network_table = containers.get("network")
    if network_table:
        if progress:
            progress.set_stage("render-container-networks", "rendering container networks")
        r, ru = render_networks(network_table, render_root)
        rendered_units.update(r)
        runtime_units.extend(ru)

    volume_table = containers.get("volume")
    if volume_table:
        if progress:
            progress.set_stage("render-container-volumes", "rendering container volumes")
        r, ru = render_volumes(
            volume_table, render_root, infer_volume_modes(container_table, volume_table)
        )
        rendered_units.update(r)
        runtime_units.extend(ru)

    build_table = containers.get("build")
    if build_table:
        if progress:
            progress.set_stage("render-container-builds", "rendering container builds")
        r, ru = render_builds(
            build_table, render_root, infer_build_modes(container_table, build_table)
        )
        rendered_units.update(r)
        runtime_units.extend(ru)

    validate_unique_runtime_services(runtime_units)

    if progress:
        progress.set_stage("write-quadlets", "writing container unit files")
    quadlet_dir = config_root / "quadlet"
    quadlet_dir.mkdir(parents=True, exist_ok=True)
    for existing in quadlet_dir.iterdir():
        if existing.is_file():
            existing.unlink()
    for filename, content in rendered_units.items():
        unit_path = quadlet_dir / filename
        unit_path.write_text(content)
        unit_path.chmod(0o644)

    if progress:
        progress.set_stage("write-runtime-metadata", "writing container runtime metadata")
    runtime_metadata = {
        "app_user": APP_RUNTIME_USER,
        "rootless_network": ROOTLESS_NETWORK_NAME,
        "units": runtime_units,
    }
    metadata_path = config_root / RUNTIME_METADATA_FILENAME
    metadata_path.write_text(json.dumps(runtime_metadata, indent=2) + "\n")
    metadata_path.chmod(0o600)

    if os.geteuid() == 0:
        _grant_service_read_access(config_root)

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
    is_reapply = _has_first_config_marker(config_root)
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
                parsed, config_path, files_path, candidate_root, config_root, progress
            )
        except Exception:
            shutil.rmtree(candidate_root, ignore_errors=True)
            raise
        if progress:
            progress.set_stage("promote", "activating initial config root")
        _write_first_config_marker(candidate_root)
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
            parsed, config_path, files_path, candidate_root, config_root, progress
        )
        carry_forward_managed_state(config_root, candidate_root)
        if _has_first_config_marker(config_root):
            shutil.copyfile(
                _first_config_marker_path(config_root),
                _first_config_marker_path(candidate_root),
            )
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


def _copy_candidate_to_durable(candidate_root: Path, durable_candidate: Path) -> None:
    if durable_candidate.exists():
        shutil.rmtree(durable_candidate)
    shutil.copytree(candidate_root, durable_candidate, symlinks=False)
    for current in [durable_candidate, *durable_candidate.rglob("*")]:
        current_stat = current.lstat()
        if stat.S_ISLNK(current_stat.st_mode):
            raise ProvisionError(f"durable candidate must not contain symlink: {current}")
        os.chown(current, 0, 0, follow_symlinks=False)
        if stat.S_ISDIR(current_stat.st_mode):
            current.chmod(0o755)
        elif stat.S_ISREG(current_stat.st_mode):
            current.chmod(stat.S_IMODE(current_stat.st_mode) & 0o777)
        else:
            raise ProvisionError(
                f"durable candidate must contain only files/directories: {current}"
            )


def _copy_staged_job_snapshot(source: Path, destination: Path, job_id: str) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    manifest = _read_staged_snapshot_manifest(source, job_id)
    destination.mkdir(parents=True, exist_ok=True)
    destination.chmod(0o700)
    write_json_atomic(destination / "manifest.json", manifest)
    _copy_staged_manifest_tree(source, destination, "candidate", manifest.get("candidate", []))
    bundle_entries = manifest.get("bundle_files", [])
    if bundle_entries or manifest.get("bundle_files_present") is True:
        _copy_staged_manifest_tree(source, destination, "bundle-files", bundle_entries)


def _read_staged_snapshot_manifest(source: Path, job_id: str) -> dict[str, Any]:
    manifest = read_json(source / "manifest.json")
    if manifest.get("version") != MANIFEST_VERSION:
        raise ProvisionError("unsupported staged manifest version")
    if manifest.get("job_id") != job_id:
        raise ProvisionError("staged manifest job id mismatch")
    allowed = {"manifest.json", "candidate"}
    if manifest.get("bundle_files") or manifest.get("bundle_files_present") is True:
        allowed.add("bundle-files")
    actual = {child.name for child in source.iterdir()}
    unexpected = actual - allowed
    if unexpected:
        raise ProvisionError(
            "staged job contains unexpected top-level entries: "
            + ", ".join(sorted(unexpected))
        )
    if not (source / "candidate").is_dir():
        raise ProvisionError("staged job missing candidate directory")
    return manifest


def _manifest_nonnegative_int(manifest: dict[str, Any], key: str) -> int:
    value = manifest.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ProvisionError(f"staged manifest {key} must be a non-negative integer")
    return value


def _render_verified_staged_candidate_sync(
    snapshot: Path,
    config_root: Path,
    manifest: dict[str, Any],
    progress: ProgressReporter | None = None,
) -> dict[str, Any]:
    source_config = snapshot / "candidate" / "config.toml"
    expected_digest = manifest.get("source_sha256")
    if not isinstance(expected_digest, str) or expected_digest != sha256_file(source_config):
        raise ProvisionError("staged source config hash changed")
    parsed = load_config(source_config)
    allow_reapply = _manifest_bool(manifest, "allow_reapply", default=True)
    preserve_bundle_files = _manifest_bool(manifest, "preserve_bundle_files", default=False)
    candidate_root = snapshot / "candidate-rendered"
    bundle_root = snapshot / "bundle-files"
    warnings = write_imported_state(
        parsed, source_config, None, candidate_root, config_root, progress
    )
    if _has_first_config_marker(config_root):
        carry_forward_managed_state(config_root, candidate_root)
    rendered_manifest = {
        **manifest,
        **_manifest_for_staged_candidate(
            job_id=str(manifest["job_id"]),
            config_path=source_config,
            candidate_root=candidate_root,
            bundle_root=bundle_root,
            parsed=parsed,
            warnings=warnings,
            filename="config.toml",
            source_digest=sha256_file(source_config),
            allow_reapply=allow_reapply,
            operation=str(manifest.get("operation", "full-apply")),
            is_reapply=_has_first_config_marker(config_root),
            preserve_bundle_files=preserve_bundle_files,
        ),
    }
    return _promote_pre_rendered_candidate_sync(
        candidate_root,
        bundle_root,
        config_root,
        rendered_manifest,
        progress,
    )


def _manifest_bool(manifest: dict[str, Any], key: str, *, default: bool) -> bool:
    value = manifest.get(key, default)
    if not isinstance(value, bool):
        raise ProvisionError(f"staged manifest {key} must be a boolean")
    return value


def _copy_staged_manifest_tree(
    source: Path, destination: Path, dirname: str, entries: Any
) -> None:
    if not isinstance(entries, list):
        raise ProvisionError("staged manifest tree entries must be a list")
    source_root = source / dirname
    destination_root = destination / dirname
    source_root_stat = source_root.lstat()
    if stat.S_ISLNK(source_root_stat.st_mode) or not stat.S_ISDIR(source_root_stat.st_mode):
        raise ProvisionError(f"staged path must be a directory: {source_root}")
    destination_root.mkdir(parents=True, exist_ok=True)
    destination_root.chmod(stat.S_IMODE(source_root_stat.st_mode) & 0o7777)
    for entry in sorted(entries, key=_staged_manifest_copy_sort_key):
        if not isinstance(entry, dict):
            raise ProvisionError("staged manifest tree entry must be an object")
        rel_path = validate_relative_path(entry.get("path", ""))
        entry_type = entry.get("type")
        source_path = source_root / rel_path
        destination_path = destination_root / rel_path
        if entry_type == "dir":
            _copy_staged_dir_metadata(source_path, destination_path)
        elif entry_type == "file":
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            expected_size = entry.get("size")
            if not isinstance(expected_size, int) or isinstance(expected_size, bool):
                raise ProvisionError(f"invalid staged manifest size for {rel_path}")
            _copy_staged_file_from_path(source_path, destination_path, expected_size)
        else:
            raise ProvisionError(
                f"invalid staged manifest entry type for {rel_path}: {entry_type!r}"
            )
    for entry in sorted(entries, key=_staged_manifest_copy_sort_key):
        if not isinstance(entry, dict) or entry.get("type") != "dir":
            continue
        rel_path = validate_relative_path(entry.get("path", ""))
        _copy_staged_dir_metadata(source_root / rel_path, destination_root / rel_path)


def _staged_manifest_copy_sort_key(entry: Any) -> tuple[bool, int, str]:
    if not isinstance(entry, dict):
        return True, 0, ""
    path = str(entry.get("path", ""))
    return entry.get("type") != "dir", path.count("/"), path


def _copy_staged_dir_metadata(source: Path, destination: Path) -> None:
    source_fd = os.open(
        source,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        source_stat = os.fstat(source_fd)
        if not stat.S_ISDIR(source_stat.st_mode):
            raise ProvisionError(f"staged path must be a directory: {source}")
        destination.mkdir(parents=True, exist_ok=True)
        destination.chmod(stat.S_IMODE(source_stat.st_mode) & 0o7777)
    finally:
        os.close(source_fd)


def _copy_staged_file_from_path(
    source: Path, destination: Path, expected_size: int | None = None
) -> None:
    source_fd = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        with os.fdopen(source_fd, "rb") as source_file:
            source_fd = -1
            _copy_staged_file_stream(source_file, source, destination, expected_size)
    finally:
        if source_fd >= 0:
            os.close(source_fd)


def _copy_staged_file_stream(
    source_file, source: Path, destination: Path, expected_size: int | None
) -> None:
    source_stat = os.fstat(source_file.fileno())
    if not stat.S_ISREG(source_stat.st_mode):
        raise ProvisionError(f"staged path must be a regular file: {source}")
    if expected_size is not None and source_stat.st_size != expected_size:
        raise ProvisionError(f"staged file size changed: {source}")
    copied = 0
    with destination.open("wb") as output:
        while True:
            chunk = source_file.read(1024 * 1024)
            if not chunk:
                break
            copied += len(chunk)
            if expected_size is not None and copied > expected_size:
                raise ProvisionError(f"staged file size changed: {source}")
            output.write(chunk)
    if expected_size is not None and copied != expected_size:
        raise ProvisionError(f"staged file size changed: {source}")
    destination.chmod(stat.S_IMODE(source_stat.st_mode) & 0o7777)


def _promote_pre_rendered_candidate_sync(
    candidate_root: Path,
    bundle_files_root: Path | None,
    config_root: Path,
    manifest: dict[str, Any],
    progress: ProgressReporter | None = None,
) -> dict[str, Any]:
    config_root = validate_config_root(config_root, allow_unsafe_env=False)
    recover_config_root(config_root)
    is_reapply = _has_first_config_marker(config_root)
    if is_reapply and not manifest.get("allow_reapply", True):
        message = "config already provisioned; reapply requires authenticated API access"
        raise ProvisionError(message)

    durable_candidate = candidate_root_path(config_root)
    if progress:
        progress.set_stage("write-candidate", "copying verified candidate into /data")
    _copy_candidate_to_durable(candidate_root, durable_candidate)
    if bundle_files_root is not None and bundle_files_root.exists():
        copy_bundle_files(bundle_files_root, durable_candidate)

    if is_reapply:
        if manifest.get("preserve_bundle_files") is True:
            copy_bundle_files(config_root / "files", durable_candidate)
        if _has_first_config_marker(config_root):
            shutil.copyfile(
                _first_config_marker_path(config_root),
                _first_config_marker_path(durable_candidate),
            )
        _grant_service_read_access(durable_candidate)
        if progress:
            progress.set_stage("promote", "swapping active config root")
        atomic_promote(config_root, durable_candidate)
        success, failures, rollback_status = complete_reapply(config_root, progress)
        if not success:
            error_msg = f"activation failed: {', '.join(failures)}"
            exc = ProvisionError(error_msg)
            exc.rollback_status = rollback_status  # type: ignore[attr-defined]
            raise exc
        forwarding_url = manifest.get("forwarding_url")
        lan_settings = manifest.get("lan_settings")
        if isinstance(lan_settings, dict):
            schedule_bootstrap_rebind({"lan_settings": lan_settings})
        return {
            "warnings": list(manifest.get("warnings", [])),
            "reapply": True,
            "rolled_back": False,
            "forwarding_url": forwarding_url if isinstance(forwarding_url, str) else None,
        }

    if progress:
        progress.set_stage("promote", "activating initial config root")
    _write_first_config_marker(durable_candidate)
    _grant_service_read_access(durable_candidate)
    atomic_promote_initial(config_root, durable_candidate)
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
    forwarding_url = manifest.get("forwarding_url")
    return {
        "warnings": list(manifest.get("warnings", [])),
        "reapply": False,
        "forwarding_url": forwarding_url if isinstance(forwarding_url, str) else None,
    }


def apply_staged_job(config_root: Path, runtime_root: Path | None = None) -> dict[str, Any] | None:
    """Claim and apply one staged provisioning job as the root worker."""
    config_root = validate_config_root(config_root, allow_unsafe_env=False)
    require_worker_for_data_config(config_root, "apply staged job")
    previous_worker_active = os.environ.get(PROVISION_WORKER_ACTIVE_ENV)
    os.environ[PROVISION_WORKER_ACTIVE_ENV] = "1"
    paths = runtime_paths(runtime_root or _runtime_paths().root)
    try:
        ensure_runtime_layout(paths, for_worker=True)
        claimed = claim_next_job(paths)
        if claimed is None:
            return None
        try:
            with tempfile.TemporaryDirectory(prefix="atomixos-staged-") as snapshot_dir:
                snapshot = Path(snapshot_dir) / claimed.job_id
                verify_staged_job(claimed, paths)
                _copy_staged_job_snapshot(claimed.path, snapshot, claimed.job_id)
                snapshot_job = ClaimedJob(claimed.job_id, snapshot)
                manifest = verify_staged_job(snapshot_job, paths, require_active=False)
                with provisioning_lock(config_root):
                    result = _render_verified_staged_candidate_sync(
                        snapshot, config_root, manifest
                    )
            write_result(paths, claimed.job_id, {"status": "succeeded", "result": result})
            return result
        except Exception as exc:
            payload: dict[str, Any] = {"status": "failed", "error": str(exc)}
            rollback_status = getattr(exc, "rollback_status", None)
            if isinstance(rollback_status, str):
                payload["rollback_status"] = rollback_status
            write_result(paths, claimed.job_id, payload)
            raise
        finally:
            cleanup_claimed_job(claimed)
    finally:
        if previous_worker_active is None:
            os.environ.pop(PROVISION_WORKER_ACTIVE_ENV, None)
        else:
            os.environ[PROVISION_WORKER_ACTIVE_ENV] = previous_worker_active


def finalize_staged_jobs(runtime_root: Path | None = None, reason: str | None = None) -> int:
    """Mark active staged jobs failed after an interrupted root worker."""
    paths = runtime_paths(runtime_root or _runtime_paths().root)
    return finalize_abandoned_active_jobs(
        paths, reason or "privileged apply worker stopped before writing a result"
    )


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
        if (
            staging_enabled()
            and config_root.resolve(strict=False) == Path("/data/config")
        ):
            return _stage_prepared_sync(
                _progress_job_id(progress),
                config_path,
                files_path,
                config_root,
                filename=filename,
                source_digest=sha256_file(config_path),
                allow_reapply=allow_reapply,
                progress=progress,
            )
        with provisioning_lock(config_root):
            return _provision_prepared_sync(
                config_path, files_path, config_root, progress, allow_reapply
            )
    finally:
        tmpdir.cleanup()


def _apply_config_operation_sync(
    operation: dict[str, Any],
    config_root: Path,
    progress: ProgressReporter | None = None,
) -> dict[str, Any]:
    if (
        staging_enabled()
        and config_root.resolve(strict=False) == Path("/data/config")
    ):
        job_id = _progress_job_id(progress)
        _stage_config_operation_sync(job_id, operation, config_root, progress)
        return _wait_for_staged_result(_runtime_paths(), job_id, progress)

    with provisioning_lock(config_root):
        recover_config_root(config_root)
        from atomixos_provision.partial_config import (
            apply_operation,
            canonical_config_bytes,
            load_current_config,
        )

        current = load_current_config(config_root)
        candidate = canonical_config_bytes(apply_operation(current, operation))
        tmpdir, config_path, _files_path = prepare_source_bytes(candidate, "config.toml")
        try:
            files_path = config_root / "files" if (config_root / "files").exists() else None
            return _provision_prepared_sync(config_path, files_path, config_root, progress, True)
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
        if staging_enabled() and config_root.resolve(strict=False) == Path("/data/config"):
            return _stage_prepared_sync(
                str(uuid.uuid4()),
                config_path,
                files_path,
                config_root,
                filename=config_path.name,
                source_digest=sha256_file(config_path),
            )
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


async def apply_config_operation(
    operation: dict[str, Any],
    config_root: Path,
    progress: ProgressReporter | None = None,
) -> dict[str, Any]:
    """Apply a typed partial operation under the same pipeline as full imports."""
    return await asyncio.to_thread(_apply_config_operation_sync, operation, config_root, progress)


async def stage_config_operation(
    job_id: str,
    operation: dict[str, Any],
    config_root: Path,
    progress: ProgressReporter | None = None,
) -> None:
    """Stage a typed partial operation for the privileged worker."""
    await asyncio.to_thread(_stage_config_operation_sync, job_id, operation, config_root, progress)


async def apply_config_transform(
    transform,
    config_root: Path,
    progress: ProgressReporter | None = None,
) -> dict[str, Any]:
    """Apply a config transform under the same lock and pipeline as full imports."""
    def _apply_transform_sync() -> dict[str, Any]:
        if staging_enabled() and config_root.resolve(strict=False) == Path("/data/config"):
            raise ProvisionError("config transforms for /data/config must use staged operations")
        with provisioning_lock(config_root):
            from atomixos_provision.partial_config import (
                canonical_config_bytes,
                load_current_config,
            )

            current = load_current_config(config_root)
            candidate = canonical_config_bytes(transform(current))
            tmpdir, config_path, _files_path = prepare_source_bytes(candidate, "config.toml")
            try:
                files_path = config_root / "files" if (config_root / "files").exists() else None
                return _provision_prepared_sync(
                    config_path, files_path, config_root, progress, True
                )
            finally:
                tmpdir.cleanup()

    return await asyncio.to_thread(_apply_transform_sync)


def locked_export_config_bytes(config_root: Path) -> bytes:
    """Read active config.toml under the provisioning lock."""
    from atomixos_provision.partial_config import export_config_bytes

    config_root = validate_config_root(config_root)
    with provisioning_lock(config_root):
        return export_config_bytes(config_root)


async def validate_config_bytes(
    payload: bytes, filename: str, config_root: Path
) -> dict[str, Any]:
    """Validate config bytes without applying."""
    return await asyncio.to_thread(_validate_sync, payload, filename, config_root)
