"""Quadlet unit rendering (container, network, volume, build)."""

import re
from pathlib import Path
from typing import Any

from atomixos_provision.config import (
    provision_error,
    require_allowed_keys,
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
            item_path = (
                f"{path}.{key}[{idx}]"
                if isinstance(raw_value, list)
                else f"{path}.{key}"
            )
            if isinstance(value, (list, dict)):
                message = f"expected scalar value at {item_path}"
                raise provision_error(message)
            validate_directive_value(value, item_path)
            normalized_values.append(value)
        normalized[key] = normalized_values
    return normalized


def rewrite_rootless_publish_port(
    value: str, container_name: str, warnings: list[str]
) -> str:
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


def render_section(
    section_name: str, directives: dict[str, list], config_root: Path
) -> list[str]:
    """Render a single Quadlet section as INI-style lines."""
    lines = [f"[{section_name}]"]
    for key, values in directives.items():
        for value in values:
            rendered_value = (
                substitute_tokens(value, config_root)
                if isinstance(value, str)
                else value
            )
            lines.append(f"{key}={format_scalar(rendered_value)}")
    lines.append("")
    return lines


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
        sections = require_allowed_keys(
            raw_sections,
            container_path,
            {"privileged", "Unit", "Container", "Install"},
            {"privileged", "Container"},
        )
        privileged = require_bool(
            sections.get("privileged"), f"{container_path}.privileged"
        )
        container_directives = normalize_directives(
            require_mapping(sections.get("Container"), f"{container_path}.Container"),
            f"{container_path}.Container",
        )

        image_values = container_directives.get("Image")
        if image_values is None or len(image_values) != 1:
            message = (
                f"{container_path}.Container.Image must be a single string value"
            )
            raise provision_error(message)
        require_string(image_values[0], f"{container_path}.Container.Image")

        if privileged:
            if "Network" in container_directives and container_directives[
                "Network"
            ] != ["host"]:
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
                        rewrite_rootless_publish_port(
                            port_value, container_name, warnings
                        )
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
                require_mapping(
                    sections["Install"], f"{container_path}.Install"
                ),
                f"{container_path}.Install",
            )
            lines.extend(render_section("Install", install_directives, config_root))

        filename = f"{container_name}{CONTAINER_SUFFIX}"
        rendered[filename] = "\n".join(lines).rstrip() + "\n"
        runtime_units.append({
            "name": container_name,
            "filename": filename,
            "service": f"{container_name}.service",
            "mode": runtime_mode,
        })

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
        sections = require_allowed_keys(
            raw_sections, network_path, {"Network"}, {"Network"}
        )
        network_directives = normalize_directives(
            require_mapping(sections.get("Network"), f"{network_path}.Network"),
            f"{network_path}.Network",
        )

        lines = render_section("Network", network_directives, config_root)
        filename = f"{network_name}{NETWORK_SUFFIX}"
        rendered[filename] = "\n".join(lines).rstrip() + "\n"
        runtime_units.append({
            "name": network_name,
            "filename": filename,
            "service": f"{network_name}-network.service",
            "mode": "rootful",
        })

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
        sections = require_allowed_keys(
            raw_sections, volume_path, {"Volume"}, {"Volume"}
        )
        volume_directives = normalize_directives(
            require_mapping(sections.get("Volume"), f"{volume_path}.Volume"),
            f"{volume_path}.Volume",
        )

        lines = render_section("Volume", volume_directives, config_root)
        filename = f"{volume_name}{VOLUME_SUFFIX}"
        rendered[filename] = "\n".join(lines).rstrip() + "\n"
        modes = sorted((volume_modes or {}).get(volume_name, {"rootful"}))
        for mode in modes:
            runtime_units.append({
                "name": volume_name,
                "filename": filename,
                "service": f"{volume_name}-volume.service",
                "mode": mode,
            })

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
        sections = require_allowed_keys(
            raw_sections, build_path, {"Build"}, {"Build"}
        )
        build_directives = normalize_directives(
            require_mapping(sections.get("Build"), f"{build_path}.Build"),
            f"{build_path}.Build",
        )

        lines = render_section("Build", build_directives, config_root)
        filename = f"{build_name}{BUILD_SUFFIX}"
        rendered[filename] = "\n".join(lines).rstrip() + "\n"
        modes = sorted((build_modes or {}).get(build_name, {"rootful"}))
        for mode in modes:
            runtime_units.append({
                "name": build_name,
                "filename": filename,
                "service": f"{build_name}-build.service",
                "mode": mode,
            })

    return rendered, runtime_units
