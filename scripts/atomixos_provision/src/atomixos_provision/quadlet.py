"""Quadlet unit rendering (container, network, volume, build)."""

import os
import re
import shlex
from pathlib import Path
from typing import Any

from atomixos_provision.config import (
    provision_error,
    require_bool,
    require_mapping,
    require_string,
    validate_name,
)

__all__ = [
    "render_builds",
    "render_containers",
    "render_networks",
    "render_volumes",
]

# --- Constants ---

CONFIG_DIR_TOKEN = "${CONFIG_DIR}"
FILES_DIR_TOKEN = "${FILES_DIR}"
APP_RUNTIME_USER = "appsvc"
ROOTLESS_NETWORK_NAME = "pasta"
RUNTIME_METADATA_FILENAME = "quadlet-runtime.json"

CONTAINER_SUFFIX = ".container"
NETWORK_SUFFIX = ".network"
VOLUME_SUFFIX = ".volume"
BUILD_SUFFIX = ".build"
QUADLET_SUFFIXES = frozenset(
    {".build", ".container", ".image", ".kube", ".network", ".pod", ".volume"}
)
DIRECTIVE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
VOLUME_OPTIONS = frozenset(
    {
        "ro",
        "rw",
        "z",
        "Z",
        "O",
        "U",
        "noexec",
        "exec",
        "nodev",
        "dev",
        "nosuid",
        "suid",
        "private",
        "rprivate",
        "shared",
        "rshared",
        "slave",
        "rslave",
        "unbindable",
        "runbindable",
        "bind",
        "rbind",
        "cached",
        "delegated",
        "copy",
        "nocopy",
        "no-dereference",
        "idmap",
    }
)


# --- Helpers ---


def format_scalar(value: Any) -> str:
    """Format a scalar value for Quadlet unit file output."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value
    message = f"unsupported scalar value type: {type(value).__name__}"
    raise provision_error(message)


def validate_directive_name(name: str, path: str) -> None:
    """Validate a systemd/Quadlet directive name."""
    if not DIRECTIVE_NAME_RE.fullmatch(name):
        message = f"invalid directive name at {path}: {name!r}"
        raise provision_error(message)


def validate_directive_value(value: Any, path: str) -> None:
    """Reject values that can inject extra INI lines or sections."""
    if isinstance(value, str) and any(c in value for c in "\x00\r\n"):
        message = f"invalid newline or NUL in directive value at {path}"
        raise provision_error(message)


def substitute_tokens(value: str, config_root: Path) -> str:
    """Replace ${CONFIG_DIR} and ${FILES_DIR} tokens with actual paths."""
    return value.replace(CONFIG_DIR_TOKEN, str(config_root)).replace(
        FILES_DIR_TOKEN, str(config_root / "files")
    )


def normalize_directives(directives_table: dict, path: str) -> dict[str, list]:
    """Normalize directive values to lists and validate scalar types."""
    normalized: dict[str, list] = {}
    for key, raw_value in directives_table.items():
        validate_directive_name(key, f"{path}.{key}")
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        if not values:
            continue

        normalized_values: list[Any] = []
        for idx, value in enumerate(values):
            item_path = f"{path}.{key}[{idx}]" if isinstance(raw_value, list) else f"{path}.{key}"
            if isinstance(value, (list, dict)):
                message = f"expected scalar value at {item_path}"
                raise provision_error(message)
            validate_directive_value(value, item_path)
            normalized_values.append(value)
        normalized[key] = normalized_values
    return normalized


def rewrite_rootless_publish_port(value: str, container_name: str, warnings: list[str]) -> str:
    """Rewrite non-loopback PublishPort binds to 127.0.0.1 for rootless containers."""
    if value.startswith("["):
        host_end = value.find("]")
        if host_end == -1 or host_end + 1 >= len(value) or value[host_end + 1] != ":":
            return value
        bind_host = value[: host_end + 1]
        remainder = value[host_end + 2 :]
    else:
        parts = value.split(":")
        if len(parts) == 2:
            if not parts[0].isdigit():
                message = (
                    f"container.{container_name}.Container.PublishPort must include "
                    "a numeric host port for rootless containers"
                )
                raise provision_error(message)
            return f"127.0.0.1:{value}"
        if len(parts) < 3:
            message = (
                f"container.{container_name}.Container.PublishPort must include "
                "an explicit host port for rootless containers"
            )
            raise provision_error(message)
        bind_host = parts[0]
        remainder = ":".join(parts[1:])

    if bind_host in {"127.0.0.1", "127.0.1.1"}:
        return value
    if bind_host in {"localhost", "::1", "[::1]"}:
        return f"127.0.0.1:{remainder}"

    warnings.append(
        f"container.{container_name}.Container.PublishPort rewrote "
        f"non-loopback bind {value!r} to 127.0.0.1"
    )
    return f"127.0.0.1:{remainder}"


def render_section(section_name: str, directives: dict[str, list], config_root: Path) -> list[str]:
    """Render a single Quadlet section as INI-style lines."""
    lines = [f"[{section_name}]"]
    for key, values in directives.items():
        for value in values:
            rendered_value = (
                substitute_tokens(value, config_root) if isinstance(value, str) else value
            )
            lines.append(f"{key}={format_scalar(rendered_value)}")
    lines.append("")
    return lines


def _require_absolute_source(source: str, value: str) -> str:
    """Reject relative host sources whose base directory differs by mount form.

    Quadlet resolves relative ``Volume=``/``Mount=`` sources from the installed
    unit directory, while ``PodmanArgs`` resolves them from the service working
    directory, so neither can be classified from the provisioning process.
    """
    if not source.startswith(("/", CONFIG_DIR_TOKEN, FILES_DIR_TOKEN)):
        raise provision_error(
            f"relative host mount source {source!r} in {value!r} is not supported; "
            f"use an absolute path, {CONFIG_DIR_TOKEN}, or {FILES_DIR_TOKEN}"
        )
    return source


def _mount_source(directive: str, value: str) -> str | None:
    """Return a host mount source, excluding Podman named-volume identifiers."""
    if directive in {"Volume", "PodmanArgsVolume"}:
        source = value.split(":", 1)[0].strip()
        if source.startswith(("/", ".", CONFIG_DIR_TOKEN, FILES_DIR_TOKEN)):
            return _require_absolute_source(source, value)
        return None
    if directive in {"Mount", "PodmanArgsMount"}:
        source = None
        mount_type = None
        for option in value.split(","):
            key, separator, raw_value = option.partition("=")
            if not separator:
                continue
            normalized_key = key.strip().lower()
            if normalized_key == "type":
                mount_type = raw_value.strip().lower()
            elif normalized_key in {"source", "src"} and source is None:
                source = raw_value.strip()
        if mount_type not in {None, "bind", "glob"} or source is None:
            return None
        return _require_absolute_source(source, value)
    return None


def _lexical_absolute_path(path: str | Path) -> Path:
    """Normalize a Linux absolute path lexically without following symlinks."""
    # POSIX abspath preserves exactly two leading slashes; Linux treats them
    # as the same filesystem root as a single slash.
    return Path("/" + os.path.abspath(os.fspath(path)).lstrip("/"))


def _managed_file_source(source: str, config_root: Path | None) -> bool:
    """Return whether a mount source lexically overlaps the managed files root."""
    if config_root is None:
        # Preserve detection for tokenized configs for callers that do not have
        # the runtime root available. Absolute paths require that context.
        for token in (FILES_DIR_TOKEN, CONFIG_DIR_TOKEN):
            if source == token or source.startswith(f"{token}/"):
                files_root = Path(f"{CONFIG_DIR_TOKEN}/files")
                source_path = Path(
                    os.path.normpath(source.replace(FILES_DIR_TOKEN, str(files_root)))
                )
                return (
                    source_path == files_root
                    or files_root in source_path.parents
                    or source_path in files_root.parents
                )
        return False

    files_root = _lexical_absolute_path(config_root / "files")
    source_path = _lexical_absolute_path(substitute_tokens(source, config_root))
    return (
        source_path == files_root
        or files_root in source_path.parents
        or source_path in files_root.parents
    )


def managed_file_mount_warning(
    directive: str, value: str, path: str, config_root: Path | None = None
) -> str | None:
    """Warn when managed bundle files may be changed by a container."""
    source = _mount_source(directive, value)
    if source is None or not _managed_file_source(source, config_root):
        return None

    read_only = managed_file_mount_is_read_only(directive, value)
    if read_only:
        return None
    return (
        f"{path} mounts managed bundle files without a clearly read-only mount; "
        "managed bundle files are deployment inputs, so use a Podman volume "
        "for mutable runtime data"
    )


def managed_file_mount_is_read_only(directive: str, value: str) -> bool:
    """Return whether a managed-file mount explicitly requests read-only access.

    Podman's structured mount syntax treats ``ro``/``readonly`` and
    ``rw``/``readwrite`` as boolean aliases.  Track both sides explicitly so
    that false values are meaningful rather than being mistaken for an absent
    option.  An explicit writable request remains dominant for this safety
    check when contradictory options are supplied.
    """
    if directive in {"Volume", "PodmanArgsVolume"}:
        parts = value.split(":", 2)
        volume_options = set(parts[2].split(",")) if len(parts) == 3 else set()
        for option in volume_options:
            if option not in VOLUME_OPTIONS and not option.startswith(
                ("idmap=", "upperdir=", "workdir=")
            ):
                raise provision_error(f"invalid Podman volume option: {option!r}")
        return "ro" in volume_options and not {"rw", "U"}.intersection(volume_options)

    read_only = False
    writable = False
    for option in value.split(","):
        key, separator, raw_value = option.partition("=")
        normalized_key = key.strip().lower()
        if normalized_key in {"ro", "readonly"}:
            if not separator or raw_value.strip().lower() == "true":
                read_only = True
            elif raw_value.strip().lower() == "false":
                writable = True
        elif normalized_key in {"rw", "readwrite"}:
            if not separator or raw_value.strip().lower() == "true":
                writable = True
            elif raw_value.strip().lower() == "false":
                read_only = True
        elif normalized_key in {"u", "chown"} and (
            not separator or raw_value.strip().lower() == "true"
        ):
            writable = True

    return read_only and not writable


def _podman_mount_values(values: list[str]):
    """Yield mount arguments carried by PodmanArgs."""
    tokens: list[tuple[str, int]] = []
    for index, raw_value in enumerate(values):
        try:
            tokens.extend((token, index) for token in shlex.split(raw_value))
        except ValueError as exc:
            raise provision_error(f"invalid PodmanArgs[{index}] quoting: {exc}") from exc
    for position, (value, index) in enumerate(tokens):
        for option in ("--volume=", "-v=", "--mount="):
            if value.startswith(option):
                yield option.rstrip("=").lstrip("-"), value[len(option) :], index
                break
        else:
            if value.startswith("-v") and len(value) > 2:
                yield "v", value[2:], index
                continue
            for option in ("--volume", "-v", "--mount"):
                if value == option and position + 1 < len(tokens):
                    mount_value, mount_index = tokens[position + 1]
                    yield option.lstrip("-"), mount_value, mount_index
                    break


def managed_files_are_writable(
    container_table: dict[str, Any], config_root: Path | None = None
) -> bool:
    """Return whether any configured managed-file mount needs host write access."""
    writable = False
    for raw_sections in container_table.values():
        if not isinstance(raw_sections, dict):
            continue
        container = raw_sections.get("Container")
        if not isinstance(container, dict):
            continue
        for directive in ("Volume", "Mount"):
            raw_values = container.get(directive, [])
            if isinstance(raw_values, str):
                raw_values = [raw_values]
            for value in raw_values:
                if (
                    isinstance(value, str)
                    and (source := _mount_source(directive, value)) is not None
                    and _managed_file_source(source, config_root)
                    and not managed_file_mount_is_read_only(directive, value)
                ):
                    writable = True
        raw_podman_args = container.get("PodmanArgs", [])
        if isinstance(raw_podman_args, str):
            raw_podman_args = [raw_podman_args]
        podman_args = [value for value in raw_podman_args if isinstance(value, str)]
        for value, mount_value, _index in _podman_mount_values(podman_args):
            directive = "Volume" if value in {"volume", "v"} else "Mount"
            source = _mount_source(
                "PodmanArgsVolume" if directive == "Volume" else "PodmanArgsMount",
                mount_value,
            )
            if (
                source is not None
                and _managed_file_source(source, config_root)
                and not managed_file_mount_is_read_only(directive, mount_value)
            ):
                writable = True
    return writable


# --- Main Render Functions ---


def render_containers(
    container_table: dict, config_root: Path
) -> tuple[dict[str, str], list[dict[str, str]], list[str]]:
    """Render container Quadlet units.

    Returns:
        Tuple of (rendered_files, runtime_units, warnings).
    """
    rendered: dict[str, str] = {}
    runtime_units: list[dict[str, str]] = []
    warnings: list[str] = []

    if not container_table:
        message = "container must define at least one container"
        raise provision_error(message)

    for container_name, raw_sections in container_table.items():
        validate_name(container_name)
        container_path = f"container.{container_name}"
        sections = require_mapping(raw_sections, container_path)
        privileged = require_bool(sections.get("privileged"), f"{container_path}.privileged")
        container_directives = normalize_directives(
            require_mapping(sections.get("Container"), f"{container_path}.Container"),
            f"{container_path}.Container",
        )

        image_values = container_directives.get("Image")
        if image_values is None or len(image_values) != 1:
            message = f"{container_path}.Container.Image must be a single string value"
            raise provision_error(message)
        require_string(image_values[0], f"{container_path}.Container.Image")
        for directive in ("Volume", "Mount"):
            for idx, value in enumerate(container_directives.get(directive, [])):
                mount_path = f"{container_path}.Container.{directive}[{idx}]"
                warning = managed_file_mount_warning(
                    directive, require_string(value, mount_path), mount_path, config_root
                )
                if warning is not None:
                    warnings.append(warning)
        podman_args = container_directives.get("PodmanArgs", [])
        for directive, value, idx in _podman_mount_values(
            [
                require_string(value, f"{container_path}.Container.PodmanArgs[{idx}]")
                for idx, value in enumerate(podman_args)
            ]
        ):
            mount_path = f"{container_path}.Container.PodmanArgs[{idx}]"
            warning = managed_file_mount_warning(
                "PodmanArgsVolume" if directive in {"volume", "v"} else "PodmanArgsMount",
                value,
                mount_path,
                config_root,
            )
            if warning is not None:
                warnings.append(warning)

        if privileged:
            if "Network" in container_directives and container_directives["Network"] != ["host"]:
                warnings.append(
                    f"container.{container_name}.Container.Network overridden "
                    "to host for privileged container"
                )
            container_directives["Network"] = ["host"]
            runtime_mode = "rootful"
        else:
            if "Network" in container_directives:
                warnings.append(
                    f"container.{container_name}.Container.Network overridden to "
                    f"{ROOTLESS_NETWORK_NAME} for rootless container"
                )
            container_directives["Network"] = [ROOTLESS_NETWORK_NAME]
            publish_ports = container_directives.get("PublishPort", [])
            if publish_ports:
                rewritten_ports = []
                for idx, value in enumerate(publish_ports):
                    port_value = require_string(
                        value,
                        f"{container_path}.Container.PublishPort[{idx}]",
                    )
                    rewritten_ports.append(
                        rewrite_rootless_publish_port(port_value, container_name, warnings)
                    )
                container_directives["PublishPort"] = rewritten_ports
            runtime_mode = "rootless"

        lines: list[str] = []
        if "Unit" in sections:
            unit_directives = normalize_directives(
                require_mapping(sections["Unit"], f"{container_path}.Unit"),
                f"{container_path}.Unit",
            )
            lines.extend(render_section("Unit", unit_directives, config_root))

        lines.extend(render_section("Container", container_directives, config_root))

        if "Install" in sections:
            install_directives = normalize_directives(
                require_mapping(sections["Install"], f"{container_path}.Install"),
                f"{container_path}.Install",
            )
            lines.extend(render_section("Install", install_directives, config_root))

        filename = f"{container_name}{CONTAINER_SUFFIX}"
        rendered[filename] = "\n".join(lines).rstrip() + "\n"
        runtime_units.append(
            {
                "name": container_name,
                "filename": filename,
                "service": f"{container_name}.service",
                "mode": runtime_mode,
            }
        )

    return rendered, runtime_units, warnings


def render_networks(
    network_table: dict, config_root: Path
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Render network Quadlet units. Returns (rendered_files, runtime_units)."""
    rendered: dict[str, str] = {}
    runtime_units: list[dict[str, str]] = []
    if not network_table:
        return rendered, runtime_units

    for network_name, raw_sections in network_table.items():
        validate_name(network_name)
        network_path = f"network.{network_name}"
        sections = require_mapping(raw_sections, network_path)
        network_directives = normalize_directives(
            require_mapping(sections.get("Network"), f"{network_path}.Network"),
            f"{network_path}.Network",
        )

        lines = render_section("Network", network_directives, config_root)
        filename = f"{network_name}{NETWORK_SUFFIX}"
        rendered[filename] = "\n".join(lines).rstrip() + "\n"
        runtime_units.append(
            {
                "name": network_name,
                "filename": filename,
                "service": f"{network_name}-network.service",
                "mode": "rootful",
            }
        )

    return rendered, runtime_units


def render_volumes(
    volume_table: dict, config_root: Path, volume_modes: dict[str, set[str]] | None = None
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Render volume Quadlet units. Returns (rendered_files, runtime_units)."""
    rendered: dict[str, str] = {}
    runtime_units: list[dict[str, str]] = []
    if not volume_table:
        return rendered, runtime_units

    for volume_name, raw_sections in volume_table.items():
        validate_name(volume_name)
        volume_path = f"volume.{volume_name}"
        sections = require_mapping(raw_sections, volume_path)
        volume_directives = normalize_directives(
            require_mapping(sections.get("Volume"), f"{volume_path}.Volume"),
            f"{volume_path}.Volume",
        )

        lines = render_section("Volume", volume_directives, config_root)
        filename = f"{volume_name}{VOLUME_SUFFIX}"
        rendered[filename] = "\n".join(lines).rstrip() + "\n"
        modes = sorted((volume_modes or {}).get(volume_name, {"rootful"}))
        for mode in modes:
            runtime_units.append(
                {
                    "name": volume_name,
                    "filename": filename,
                    "service": f"{volume_name}-volume.service",
                    "mode": mode,
                }
            )

    return rendered, runtime_units


def render_builds(
    build_table: dict, config_root: Path, build_modes: dict[str, set[str]] | None = None
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Render build Quadlet units. Returns (rendered_files, runtime_units)."""
    rendered: dict[str, str] = {}
    runtime_units: list[dict[str, str]] = []
    if not build_table:
        return rendered, runtime_units

    for build_name, raw_sections in build_table.items():
        validate_name(build_name)
        build_path = f"build.{build_name}"
        sections = require_mapping(raw_sections, build_path)
        build_directives = normalize_directives(
            require_mapping(sections.get("Build"), f"{build_path}.Build"),
            f"{build_path}.Build",
        )

        lines = render_section("Build", build_directives, config_root)
        filename = f"{build_name}{BUILD_SUFFIX}"
        rendered[filename] = "\n".join(lines).rstrip() + "\n"
        modes = sorted((build_modes or {}).get(build_name, {"rootful"}))
        for mode in modes:
            runtime_units.append(
                {
                    "name": build_name,
                    "filename": filename,
                    "service": f"{build_name}-build.service",
                    "mode": mode,
                }
            )

    return rendered, runtime_units
