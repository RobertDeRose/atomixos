"""Typed partial config update helpers."""

import json
import re
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any

from atomixos_provision.config import provision_error, validate_name, validate_username

__all__ = [
    "delete_resource",
    "delete_user",
    "export_config_bytes",
    "load_current_config",
    "patch_network",
    "put_resource",
    "put_user",
]

_BARE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def load_current_config(config_root: Path) -> dict[str, Any]:
    config_path = config_root / "config.toml"
    if not config_path.is_file():
        raise provision_error("current config.toml not found")
    try:
        return tomllib.loads(config_path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise provision_error(f"invalid current config.toml: {exc}") from exc


def export_config_bytes(config_root: Path) -> bytes:
    config_path = config_root / "config.toml"
    if not config_path.is_file():
        raise provision_error("current config.toml not found")
    return config_path.read_bytes()


def put_user(config: dict[str, Any], name: str, payload: dict[str, Any]) -> dict[str, Any]:
    validate_username(name)
    user = _require_payload(payload, {"isAdmin", "ssh_key", "shell"})
    if "isAdmin" not in user:
        raise provision_error("user payload missing required key: isAdmin")
    updated = deepcopy(config)
    users = updated.setdefault("users", {})
    users[name] = user
    return updated


def delete_user(config: dict[str, Any], name: str) -> dict[str, Any]:
    validate_username(name)
    updated = deepcopy(config)
    users = updated.setdefault("users", {})
    users.pop(name, None)
    return updated


def patch_network(config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    network = _require_payload(
        payload,
        {
            "dns_servers",
            "dns_search_domains",
            "default_gateway",
            "interfaces",
            "dnsmasq",
            "ntp",
            "firewall",
        },
    )
    updated = deepcopy(config)
    current = updated.setdefault("network", {})
    _deep_merge(current, network)
    return updated


def put_resource(
    config: dict[str, Any], table: str, name: str, payload: dict[str, Any]
) -> dict[str, Any]:
    validate_name(name)
    resource = _require_payload(payload, None)
    if table == "container":
        _require_payload(resource, {"privileged", "Unit", "Container", "Install"})
        if "privileged" not in resource:
            raise provision_error("container payload missing required key: privileged")
        if "Container" not in resource:
            raise provision_error("container payload missing required key: Container")
    elif table == "network":
        _require_payload(resource, {"Network"})
        if "Network" not in resource:
            raise provision_error("network payload missing required key: Network")
    elif table == "volume":
        _require_payload(resource, {"Volume"})
        if "Volume" not in resource:
            raise provision_error("volume payload missing required key: Volume")
    updated = deepcopy(config)
    containers = updated.setdefault("containers", {})
    resources = containers.setdefault(table, {})
    resources[name] = resource
    return updated


def delete_resource(config: dict[str, Any], table: str, name: str) -> dict[str, Any]:
    validate_name(name)
    updated = deepcopy(config)
    containers = updated.setdefault("containers", {})
    resources = containers.setdefault(table, {})
    resources.pop(name, None)
    return updated


def canonical_config_bytes(config: dict[str, Any]) -> bytes:
    return (_dumps_toml(config).strip() + "\n").encode()


def _require_payload(
    payload: dict[str, Any], allowed_keys: set[str] | None
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise provision_error("partial request body must be a JSON object")
    if allowed_keys is not None:
        extra = set(payload) - allowed_keys
        if extra:
            raise provision_error("unsupported partial request keys: " + ", ".join(sorted(extra)))
    return payload


def _deep_merge(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if value is None:
            target.pop(key, None)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


def _dumps_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    scalars = {key: value for key, value in data.items() if not isinstance(value, dict)}
    for key, value in scalars.items():
        lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    for key, value in data.items():
        if isinstance(value, dict):
            _append_table(lines, [key], value)
    return "\n".join(lines)


def _append_table(lines: list[str], path: list[str], table: dict[str, Any]) -> None:
    scalars = {key: value for key, value in table.items() if not isinstance(value, dict)}
    if scalars or not table:
        if lines:
            lines.append("")
        lines.append("[" + ".".join(_toml_key(part) for part in path) + "]")
        for key, value in scalars.items():
            lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    for key, value in table.items():
        if isinstance(value, dict):
            _append_table(lines, [*path, key], value)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise provision_error(f"unsupported value in canonical TOML: {value!r}")


def _toml_key(value: str) -> str:
    if _BARE_KEY_RE.match(value):
        return value
    return json.dumps(value)
