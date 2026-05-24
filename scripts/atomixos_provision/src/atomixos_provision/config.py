"""config.toml parsing and schema validation."""

import ipaddress
import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

__all__ = [
    "ProvisionError",
    "load_config",
    "load_config_schema",
    "validate_against_schema",
]

# --- Constants ---

SCHEMA_ENV = "ATOMIXOS_CONFIG_SCHEMA"

DEFAULT_LAN_GATEWAY_CIDR = "172.20.30.1/24"
DEFAULT_LAN_DHCP_START = "172.20.30.10"
DEFAULT_LAN_DHCP_END = "172.20.30.254"
DEFAULT_LAN_DOMAIN = "local"
DEFAULT_LAN_GATEWAY_ALIASES = ["atomixos"]
DEFAULT_LAN_HOSTNAME_PATTERN = ""
DEFAULT_NTP_SERVERS = ["time.cloudflare.com"]
SUPPORTED_INTERFACE_RE = re.compile(r"eth[0-9]+")

RESERVED_USERNAMES = frozenset(
    {
        "appsvc",
        "bin",
        "chrony",
        "daemon",
        "dnsmasq",
        "nobody",
        "root",
        "systemd-network",
        "systemd-resolve",
        "systemd-timesync",
    }
)

SSH_KEY_TYPES = frozenset(
    {
        "ecdsa-sha2-nistp256",
        "ecdsa-sha2-nistp384",
        "ecdsa-sha2-nistp521",
        "sk-ecdsa-sha2-nistp256@openssh.com",
        "ssh-ed25519",
        "sk-ssh-ed25519@openssh.com",
        "ssh-rsa",
    }
)


# --- Error Handling ---


class ProvisionError(RuntimeError):
    """Raised when config parsing or validation fails."""


def provision_error(message: str) -> ProvisionError:
    return ProvisionError(message)


# --- Schema Loading ---


def load_config_schema() -> dict[str, Any]:
    """Locate and load the JSON schema for config.toml validation."""
    candidates: list[Path] = []
    env_path = os.environ.get(SCHEMA_ENV)
    if env_path:
        candidates.append(Path(env_path))

    script_path = Path(__file__).resolve()
    # __file__ is src/atomixos_provision/config.py
    # 5 parents: atomixos_provision → src → atomixos_provision(pkg) → scripts → repo root
    repo_root = script_path.parent.parent.parent.parent.parent
    candidates.extend(
        [
            repo_root / "share" / "atomixos" / "config.schema.json",
            repo_root / "schemas" / "config.schema.json",
        ]
    )

    for candidate in candidates:
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text())
            except json.JSONDecodeError as exc:
                message = f"invalid config schema in {candidate}: {exc}"
                raise provision_error(message) from exc

    searched = ", ".join(str(c) for c in candidates)
    message = f"unable to find config schema (checked: {searched})"
    raise provision_error(message)


# --- Schema Validation Engine ---


def resolve_schema_ref(schema: dict, ref: str) -> dict:
    """Resolve a JSON Schema $ref pointer."""
    if not ref.startswith("#/"):
        message = f"unsupported schema ref: {ref}"
        raise provision_error(message)

    target: Any = schema
    for part in ref[2:].split("/"):
        if not isinstance(target, dict) or part not in target:
            message = f"unresolvable schema ref: {ref}"
            raise provision_error(message)
        target = target[part]
    return target


def validate_schema_property_name(name: str, schema: dict, path: str) -> None:
    """Validate a property name against a propertyNames schema."""
    expected_type = schema.get("type")
    if expected_type == "string" and not isinstance(name, str):
        msg = f"expected string property name at {path}"
        raise provision_error(msg)
    pattern = schema.get("pattern")
    if pattern and not re.fullmatch(pattern, name):
        msg = f"invalid property name at {path}: {name!r}"
        raise provision_error(msg)


def validate_against_schema(value: Any, schema: dict, path: str, root_schema: dict) -> None:
    """Recursively validate a value against a JSON Schema subset."""
    if "$ref" in schema:
        validate_against_schema(
            value, resolve_schema_ref(root_schema, schema["$ref"]), path, root_schema
        )
        return

    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try:
                validate_against_schema(value, option, path, root_schema)
                return
            except ProvisionError:
                continue
        msg = f"value at {path} does not match any allowed schema"
        raise provision_error(msg)

    expected_type = schema.get("type")
    if expected_type is not None:
        allowed_types = expected_type if isinstance(expected_type, list) else [expected_type]
        type_checks: dict[str, Any] = {
            "object": lambda v: isinstance(v, dict),
            "array": lambda v: isinstance(v, list),
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
        }
        matches_type = any(
            check(value) for allowed in allowed_types if (check := type_checks.get(allowed))
        )
        if not matches_type:
            names = ", ".join(allowed_types)
            msg = f"expected {names} at {path}"
            raise provision_error(msg)

    if "enum" in schema and value not in schema["enum"]:
        msg = f"unexpected value at {path}: {value!r}"
        raise provision_error(msg)

    if isinstance(value, dict):
        _validate_dict_schema(value, schema, path, root_schema)

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if min_items is not None and len(value) < min_items:
            msg = f"expected at least {min_items} items at {path}"
            raise provision_error(msg)
        item_schema = schema.get("items")
        if item_schema is not None:
            for idx, item in enumerate(value):
                validate_against_schema(item, item_schema, f"{path}[{idx}]", root_schema)

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if min_length is not None and len(value) < min_length:
            msg = f"expected non-empty string at {path}"
            raise provision_error(msg)

    if isinstance(value, int) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            msg = f"expected integer >= {minimum} at {path}"
            raise provision_error(msg)
        if maximum is not None and value > maximum:
            msg = f"expected integer <= {maximum} at {path}"
            raise provision_error(msg)


def _validate_dict_schema(value: dict, schema: dict, path: str, root_schema: dict) -> None:
    """Validate dict-specific schema constraints."""
    min_properties = schema.get("minProperties")
    if min_properties is not None and len(value) < min_properties:
        msg = f"expected at least {min_properties} keys at {path}"
        raise provision_error(msg)

    required = set(schema.get("required", []))
    missing = required - set(value)
    if missing:
        keys = ", ".join(sorted(missing))
        msg = f"missing required keys at {path}: {keys}"
        raise provision_error(msg)

    property_names = schema.get("propertyNames")
    if property_names is not None:
        for key in value:
            validate_schema_property_name(key, property_names, path)

    properties = schema.get("properties", {})
    additional = schema.get("additionalProperties", True)
    for key, item in value.items():
        item_path = f"{path}.{key}"
        if key in properties:
            validate_against_schema(item, properties[key], item_path, root_schema)
        elif additional is False:
            msg = f"unsupported keys at {path}: {key}"
            raise provision_error(msg)
        elif isinstance(additional, dict):
            validate_against_schema(item, additional, item_path, root_schema)


# --- Typed Validation Helpers ---


def validate_name(name: str) -> str:
    """Validate a Quadlet unit name."""
    message = f"invalid quadlet unit name: {name!r}"
    if (
        not name
        or not (name[0].isalnum() or name[0] == "_")
        or "/" in name
        or "\x00" in name
        or "." in name
        or name in {".", ".."}
    ):
        raise provision_error(message)
    for char in name:
        if not (char.isalnum() or char in {"_", "-"}):
            raise provision_error(message)
    return name


def validate_username(name: str) -> str:
    """Validate a system username."""
    message = f"invalid user name: {name!r}"
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", name):
        raise provision_error(message)
    if name in RESERVED_USERNAMES:
        message = f"reserved user name: {name!r}"
        raise provision_error(message)
    return name


def require_mapping(value: Any, path: str) -> dict:
    """Require value is a dict (TOML table)."""
    if not isinstance(value, dict):
        message = f"expected table at {path}"
        raise provision_error(message)
    return value


def require_allowed_keys(
    value: Any,
    path: str,
    allowed: set[str],
    required: set[str] | None = None,
) -> dict:
    """Require value is a dict with only allowed keys and all required keys present."""
    table = require_mapping(value, path)
    unexpected = set(table) - allowed
    if unexpected:
        keys = ", ".join(sorted(unexpected))
        message = f"unsupported keys at {path}: {keys}"
        raise provision_error(message)

    if required is not None:
        missing = required - set(table)
        if missing:
            keys = ", ".join(sorted(missing))
            message = f"missing required keys at {path}: {keys}"
            raise provision_error(message)

    return table


def require_string(value: Any, path: str) -> str:
    """Require a non-empty string value."""
    if not isinstance(value, str) or not value.strip():
        message = f"expected non-empty string at {path}"
        raise provision_error(message)
    return value.strip()


def require_string_list(value: Any, path: str) -> list[str]:
    """Require a non-empty list of non-empty strings."""
    if not isinstance(value, list) or not value:
        message = f"expected non-empty array at {path}"
        raise provision_error(message)
    result = []
    for idx, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            message = f"expected non-empty string at {path}[{idx}]"
            raise provision_error(message)
        result.append(item.strip())
    return result


def require_ssh_public_key(value: Any, path: str) -> str:
    """Require a single OpenSSH public key line."""
    key = require_string(value, path)
    if any(ord(char) < 32 or ord(char) == 127 for char in key):
        message = f"invalid SSH public key at {path}: control characters are not allowed"
        raise provision_error(message)
    parts = key.split()
    if len(parts) < 2:
        message = f"invalid SSH public key at {path}"
        raise provision_error(message)
    if parts[0] not in SSH_KEY_TYPES:
        message = f"unsupported SSH public key type at {path}: {parts[0]}"
        raise provision_error(message)
    try:
        import base64

        key_blob = base64.b64decode(parts[1].encode("ascii"), validate=True)
    except Exception as exc:
        message = f"invalid SSH public key data at {path}"
        raise provision_error(message) from exc
    if len(key_blob) < 4:
        message = f"invalid SSH public key blob at {path}"
        raise provision_error(message)
    key_type_len = int.from_bytes(key_blob[:4], "big")
    key_type_end = 4 + key_type_len
    if key_type_len <= 0 or key_type_end > len(key_blob):
        message = f"invalid SSH public key blob at {path}"
        raise provision_error(message)
    try:
        embedded_type = key_blob[4:key_type_end].decode("ascii")
    except UnicodeDecodeError as exc:
        message = f"invalid SSH public key blob at {path}"
        raise provision_error(message) from exc
    if embedded_type != parts[0]:
        message = f"SSH public key type mismatch at {path}"
        raise provision_error(message)
    return key


def require_optional_string_list(value: Any, path: str) -> list[str]:
    """Require an optional list of non-empty strings (None → empty list)."""
    if value is None:
        return []
    if not isinstance(value, list):
        message = f"expected array at {path}"
        raise provision_error(message)

    result = []
    for idx, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            message = f"expected non-empty string at {path}[{idx}]"
            raise provision_error(message)
        result.append(item.strip())
    return result


def require_ntp_server_list(value: Any, path: str) -> list[str]:
    """Require a list of valid NTP server hostnames or IP literals."""
    servers = require_string_list(value, path)
    for idx, server in enumerate(servers):
        item_path = f"{path}[{idx}]"
        if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in server):
            message = (
                f"invalid NTP server at {item_path}: "
                "whitespace and control characters are not allowed"
            )
            raise provision_error(message)
        try:
            ipaddress.ip_address(server)
        except ValueError:
            require_dns_name(server, item_path)
    return servers


def require_bool(value: Any, path: str) -> bool:
    """Require a boolean value."""
    if not isinstance(value, bool):
        message = f"expected boolean at {path}"
        raise provision_error(message)
    return value


def require_int_range(value: Any, path: str, minimum: int, maximum: int) -> int:
    """Require an integer within an inclusive range."""
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum or value > maximum:
        message = f"expected integer in range {minimum}..{maximum} at {path}"
        raise provision_error(message)
    return value


def require_port_list(value: Any, path: str) -> list[int]:
    """Require a list of valid port integers (1-65535)."""
    if not isinstance(value, list):
        message = f"expected array at {path}"
        raise provision_error(message)

    ports = []
    for idx, item in enumerate(value):
        if not isinstance(item, int) or isinstance(item, bool) or item < 1 or item > 65535:
            message = f"expected port integer in range 1..65535 at {path}[{idx}]"
            raise provision_error(message)
        ports.append(item)
    return ports


def require_dns_name(value: Any, path: str) -> str:
    """Require a valid DNS name."""
    name = require_string(value, path).lower().rstrip(".")
    if not name:
        message = f"expected non-empty string at {path}"
        raise provision_error(message)
    if len(name) > 253:
        message = f"invalid DNS name at {path}: name is longer than 253 characters"
        raise provision_error(message)

    labels = name.split(".")
    invalid_name_message = f"invalid DNS name at {path}: {value!r}"
    for label in labels:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label):
            raise provision_error(invalid_name_message)
    return name


def require_ip_address(value: Any, path: str) -> str:
    """Require an IPv4 or IPv6 address literal."""
    raw = require_string(value, path)
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError as exc:
        message = f"invalid IP address at {path}: {raw}"
        raise provision_error(message) from exc


def require_ipv4_address(value: Any, path: str) -> str:
    """Require an IPv4 address literal."""
    raw = require_string(value, path)
    try:
        return str(ipaddress.IPv4Address(raw))
    except ValueError as exc:
        message = f"invalid IPv4 address at {path}: {raw}"
        raise provision_error(message) from exc


def require_ip_address_list(value: Any, path: str) -> list[str]:
    """Require a non-empty list of IP address literals."""
    items = require_string_list(value, path)
    return [require_ip_address(item, f"{path}[{idx}]") for idx, item in enumerate(items)]


def require_dns_search_domains(value: Any, path: str) -> list[str]:
    """Require a non-empty list of DNS search domains."""
    items = require_string_list(value, path)
    return [require_dns_name(item, f"{path}[{idx}]") for idx, item in enumerate(items)]


def validate_interface_name(name: str) -> str:
    """Validate a supported Ethernet interface name."""
    if not SUPPORTED_INTERFACE_RE.fullmatch(name):
        message = f"unsupported network interface name: {name!r}"
        raise provision_error(message)
    return name


def require_ipv4_interface(value: Any, path: str) -> ipaddress.IPv4Interface:
    """Require an IPv4 CIDR address."""
    raw = require_string(value, path)
    try:
        return ipaddress.IPv4Interface(raw)
    except ValueError as exc:
        message = f"invalid IPv4 CIDR at {path}: {raw}"
        raise provision_error(message) from exc


def require_https_url(value: Any, path: str) -> str:
    """Require an HTTPS base URL suitable for path concatenation."""
    url = require_string(value, path)
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url):
        message = f"invalid URL at {path}: whitespace/control characters are not allowed"
        raise provision_error(message)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        message = f"{path} must be an https:// URL"
        raise provision_error(message)
    try:
        _ = parsed.port
    except ValueError as exc:
        message = f"invalid URL port at {path}"
        raise provision_error(message) from exc
    if parsed.username is not None or parsed.password is not None:
        message = f"{path} must not include credentials"
        raise provision_error(message)
    if parsed.query or parsed.fragment:
        message = f"{path} must not include a query string or fragment"
        raise provision_error(message)
    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError:
        require_dns_name(parsed.hostname, path)
    return url.rstrip("/")


# --- Section Loaders ---


def load_lan_settings(lan_value: Any, path: str = "lan") -> dict[str, Any]:
    """Parse and validate LAN/dnsmasq settings."""
    if lan_value is None:
        lan_value = {}

    lan = require_allowed_keys(
        lan_value,
        path,
        {
            "gateway_cidr",
            "dhcp_start",
            "dhcp_end",
            "domain",
            "hostname_pattern",
            "gateway_aliases",
        },
    )

    gateway = require_ipv4_interface(
        lan.get("gateway_cidr", DEFAULT_LAN_GATEWAY_CIDR), f"{path}.gateway_cidr"
    )
    if not 16 <= gateway.network.prefixlen <= 30:
        message = f"{path}.gateway_cidr prefix must be between /16 and /30"
        raise provision_error(message)

    dhcp_start_raw = require_string(
        lan.get("dhcp_start", DEFAULT_LAN_DHCP_START), f"{path}.dhcp_start"
    )
    dhcp_end_raw = require_string(lan.get("dhcp_end", DEFAULT_LAN_DHCP_END), f"{path}.dhcp_end")
    try:
        dhcp_start = ipaddress.IPv4Address(dhcp_start_raw)
        dhcp_end = ipaddress.IPv4Address(dhcp_end_raw)
    except ValueError as exc:
        message = f"invalid IPv4 address in {path}.dhcp_start or {path}.dhcp_end"
        raise provision_error(message) from exc

    if dhcp_start not in gateway.network or dhcp_end not in gateway.network:
        message = f"{path}.dhcp_start and {path}.dhcp_end must be inside {gateway.network}"
        raise provision_error(message)
    if dhcp_start > dhcp_end:
        message = f"{path}.dhcp_start must be less than or equal to {path}.dhcp_end"
        raise provision_error(message)
    if dhcp_start <= gateway.ip <= dhcp_end:
        message = f"{path}.dhcp_start and {path}.dhcp_end must not include the gateway IP"
        raise provision_error(message)

    domain = require_dns_name(lan.get("domain", DEFAULT_LAN_DOMAIN), f"{path}.domain")
    hostname_pattern = (
        require_string(
            lan.get("hostname_pattern", DEFAULT_LAN_HOSTNAME_PATTERN)
            or DEFAULT_LAN_HOSTNAME_PATTERN,
            f"{path}.hostname_pattern",
        )
        if lan.get("hostname_pattern") not in (None, "")
        else DEFAULT_LAN_HOSTNAME_PATTERN
    )
    if hostname_pattern:
        if "{mac}" not in hostname_pattern:
            message = f"{path}.hostname_pattern must include {{mac}}"
            raise provision_error(message)
        pattern_probe = hostname_pattern.replace("{mac}", "001122334455")
        require_dns_name(pattern_probe, f"{path}.hostname_pattern")

    gateway_aliases = require_optional_string_list(
        lan.get("gateway_aliases"), f"{path}.gateway_aliases"
    )
    if not gateway_aliases:
        gateway_aliases = list(DEFAULT_LAN_GATEWAY_ALIASES)
    gateway_aliases = [
        require_dns_name(alias, f"{path}.gateway_aliases") for alias in gateway_aliases
    ]

    return {
        "gateway_cidr": str(gateway),
        "gateway_ip": str(gateway.ip),
        "subnet_cidr": str(gateway.network),
        "netmask": str(gateway.netmask),
        "dhcp_start": str(dhcp_start),
        "dhcp_end": str(dhcp_end),
        "domain": domain,
        "hostname_pattern": hostname_pattern,
        "gateway_aliases": list(dict.fromkeys(gateway_aliases)),
    }


def load_users(users_value: Any) -> tuple[dict[str, dict], list[str]]:
    """Parse and validate the [users] table. Returns (users_dict, admin_ssh_keys)."""
    users = require_mapping(users_value, "users")
    normalized: dict[str, dict] = {}
    admin_keys: list[str] = []

    for username, raw_user in users.items():
        validate_username(username)
        user = require_allowed_keys(raw_user, f"users.{username}", {"isAdmin", "ssh_key", "shell"})
        is_admin = require_bool(user.get("isAdmin", False), f"users.{username}.isAdmin")
        ssh_key_raw = user.get("ssh_key", "")
        if not isinstance(ssh_key_raw, str):
            message = f"expected string at users.{username}.ssh_key"
            raise provision_error(message)
        ssh_key = (
            require_ssh_public_key(ssh_key_raw, f"users.{username}.ssh_key")
            if ssh_key_raw.strip()
            else ""
        )
        shell_raw = user.get("shell")
        if shell_raw is not None and shell_raw not in {"bash", "sh", "zsh"}:
            message = f"users.{username}.shell must be one of: bash, sh, zsh"
            raise provision_error(message)
        normalized[username] = {
            "isAdmin": is_admin,
            "ssh_key": ssh_key,
        }
        if shell_raw is not None:
            normalized[username]["shell"] = shell_raw
        if is_admin and ssh_key:
            admin_keys.append(ssh_key)

    if not admin_keys:
        message = "users must define at least one admin user with a non-empty ssh_key"
        raise provision_error(message)

    return normalized, admin_keys


def load_network_settings(network_value: Any) -> dict[str, Any]:
    """Parse and validate the [network] section, returning LAN settings dict."""
    if network_value is None:
        network_value = {}
    network = require_allowed_keys(
        network_value,
        "network",
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
    dnsmasq = network.get("dnsmasq", {})
    dnsmasq_settings = require_allowed_keys(
        dnsmasq,
        "network.dnsmasq",
        {
            "enable",
            "interface",
            "gateway_cidr",
            "dhcp_start",
            "dhcp_end",
            "domain",
            "hostname_pattern",
            "gateway_aliases",
        },
    )

    if "enable" in dnsmasq_settings and not require_bool(
        dnsmasq_settings["enable"], "network.dnsmasq.enable"
    ):
        message = (
            "network.dnsmasq.enable must remain true; disabling LAN DHCP/DNS is not supported"
        )
        raise provision_error(message)
    if "interface" in dnsmasq_settings:
        interface = require_string(dnsmasq_settings["interface"], "network.dnsmasq.interface")
        if interface != "eth1":
            message = "network.dnsmasq.interface must be eth1"
            raise provision_error(message)

    lan_input = {k: v for k, v in dnsmasq_settings.items() if k not in ("enable", "interface")}
    interfaces = load_network_interfaces(network.get("interfaces"))
    eth1 = interfaces.get("eth1")
    if eth1 and eth1.get("mode") == "static":
        eth1_gateway = require_ipv4_interface(
            eth1["address"], "network.interfaces.eth1.address"
        )
        if "gateway_cidr" in lan_input:
            dnsmasq_gateway = require_ipv4_interface(
                lan_input["gateway_cidr"], "network.dnsmasq.gateway_cidr"
            )
        else:
            dnsmasq_gateway = None
        if dnsmasq_gateway is not None and dnsmasq_gateway != eth1_gateway:
            message = (
                "network.interfaces.eth1.address must match "
                "network.dnsmasq.gateway_cidr when both are set"
            )
            raise provision_error(message)
        lan_input["gateway_cidr"] = str(eth1_gateway)

    lan_settings = load_lan_settings(lan_input, "network.dnsmasq")
    ntp = require_allowed_keys(network.get("ntp", {}), "network.ntp", {"servers"})
    lan_settings["ntp_servers"] = require_ntp_server_list(
        ntp.get("servers", DEFAULT_NTP_SERVERS), "network.ntp.servers"
    )
    return lan_settings


def load_host_network_settings(network_value: Any) -> dict[str, Any]:
    """Parse and validate host resolver, route, and interface settings."""
    if network_value is None:
        network_value = {}
    network = require_allowed_keys(
        network_value,
        "network",
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
    result = {
        "dns_servers": require_ip_address_list(network["dns_servers"], "network.dns_servers")
        if "dns_servers" in network
        else [],
        "dns_search_domains": require_dns_search_domains(
            network["dns_search_domains"], "network.dns_search_domains"
        )
        if "dns_search_domains" in network
        else [],
        "interfaces": load_network_interfaces(network.get("interfaces")),
    }
    if "default_gateway" in network:
        result["default_gateway"] = require_ipv4_address(
            network["default_gateway"], "network.default_gateway"
        )
    return result


def load_network_interfaces(interfaces_value: Any) -> dict[str, dict[str, Any]]:
    """Parse and validate [network.interfaces] settings."""
    if interfaces_value is None:
        return {}
    interfaces = require_mapping(interfaces_value, "network.interfaces")
    normalized: dict[str, dict[str, Any]] = {}
    for name, raw_interface in interfaces.items():
        validate_interface_name(name)
        path = f"network.interfaces.{name}"
        interface = require_allowed_keys(
            raw_interface,
            path,
            {"mode", "address", "gateway", "dns_servers", "dns_search_domains"},
            {"mode"},
        )
        mode = require_string(interface["mode"], f"{path}.mode")
        if mode not in {"dhcp", "static"}:
            message = f"{path}.mode must be one of: dhcp, static"
            raise provision_error(message)
        if name == "eth1" and mode != "static":
            message = "network.interfaces.eth1.mode must be static because eth1 is the LAN gateway"
            raise provision_error(message)

        normalized_interface: dict[str, Any] = {"mode": mode}
        if mode == "static":
            if "address" not in interface:
                message = f"missing required keys at {path}: address"
                raise provision_error(message)
            address = require_ipv4_interface(interface["address"], f"{path}.address")
            normalized_interface["address"] = str(address)
        elif "address" in interface:
            message = f"{path}.address is only supported when mode is static"
            raise provision_error(message)

        if "gateway" in interface:
            normalized_interface["gateway"] = require_ipv4_address(
                interface["gateway"], f"{path}.gateway"
            )
        if "dns_servers" in interface:
            normalized_interface["dns_servers"] = require_ip_address_list(
                interface["dns_servers"], f"{path}.dns_servers"
            )
        if "dns_search_domains" in interface:
            normalized_interface["dns_search_domains"] = require_dns_search_domains(
                interface["dns_search_domains"], f"{path}.dns_search_domains"
            )
        normalized[name] = normalized_interface
    return normalized


def load_firewall_inbound(network_value: Any) -> dict[str, dict[str, list[int]]]:
    """Parse and validate the [network.firewall.inbound] section."""
    if network_value is None:
        network_value = {}
    network = require_allowed_keys(
        network_value,
        "network",
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
    firewall = network.get("firewall", {})
    firewall = require_allowed_keys(firewall, "network.firewall", {"inbound"})
    inbound_value = firewall.get("inbound", {})
    inbound = require_allowed_keys(inbound_value, "network.firewall.inbound", {"wan", "lan"})

    def normalize_firewall_scope(scope_value: Any, scope_path: str) -> dict[str, list[int]]:
        if scope_value is None:
            return {}
        scope = require_allowed_keys(scope_value, scope_path, {"tcp", "udp"})
        normalized: dict[str, list[int]] = {}
        if "tcp" in scope:
            tcp_ports = require_port_list(scope.get("tcp"), f"{scope_path}.tcp")
            if tcp_ports:
                normalized["tcp"] = tcp_ports
        if "udp" in scope:
            udp_ports = require_port_list(scope.get("udp"), f"{scope_path}.udp")
            if udp_ports:
                normalized["udp"] = udp_ports
        return normalized

    firewall_inbound: dict[str, dict[str, list[int]]] = {}
    wan_scope = normalize_firewall_scope(inbound.get("wan"), "network.firewall.inbound.wan")
    if 8080 in wan_scope.get("tcp", []):
        raise provision_error(
            "network.firewall.inbound.wan.tcp must not include reserved bootstrap port 8080"
        )
    if wan_scope:
        firewall_inbound["wan"] = wan_scope
    lan_scope = normalize_firewall_scope(inbound.get("lan"), "network.firewall.inbound.lan")
    if lan_scope:
        firewall_inbound["lan"] = lan_scope
    return firewall_inbound


def load_activation_policy(activation_value: Any, known_units: set[str]) -> dict[str, Any]:
    """Parse and validate activation policy."""
    activation = require_allowed_keys(
        activation_value,
        "activation",
        {"required", "timeout_seconds", "settle_seconds", "restart", "allow_degraded", "strategy"},
        {"required"},
    )
    required_units = require_string_list(activation.get("required"), "activation.required")
    restart = require_optional_string_list(activation.get("restart"), "activation.restart")
    allow_degraded = require_optional_string_list(
        activation.get("allow_degraded"), "activation.allow_degraded"
    )

    for field, units in {
        "activation.required": required_units,
        "activation.restart": restart,
        "activation.allow_degraded": allow_degraded,
    }.items():
        for unit in units:
            if unit not in known_units:
                message = f"{field} references unknown unit: {unit}"
                raise provision_error(message)

    overlap = sorted(set(required_units) & set(allow_degraded))
    if overlap:
        message = (
            "activation.allow_degraded must not include required units: " + ", ".join(overlap)
        )
        raise provision_error(message)

    strategy = activation.get("strategy", "rollback")
    if strategy != "rollback":
        message = "activation.strategy must be rollback"
        raise provision_error(message)

    return {
        "required": required_units,
        "timeout_seconds": require_int_range(
            activation.get("timeout_seconds", 300), "activation.timeout_seconds", 1, 3600
        ),
        "settle_seconds": require_int_range(
            activation.get("settle_seconds", 0), "activation.settle_seconds", 0, 300
        ),
        "restart": restart,
        "allow_degraded": allow_degraded,
        "allow_degraded_configured": "allow_degraded" in activation,
        "strategy": strategy,
    }


# --- Main Config Loader ---


def load_config(
    config_path: Path,
    *,
    config_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse and validate a config.toml file.

    Args:
        config_path: Path to the config.toml file.
        config_schema: Pre-loaded JSON schema (loaded from disk if None).

    Returns:
        Parsed and validated config dict with all sections normalized.
    """
    try:
        data = tomllib.loads(config_path.read_text())
    except tomllib.TOMLDecodeError as exc:
        message = f"invalid TOML in {config_path}: {exc}"
        raise provision_error(message) from exc

    root = require_allowed_keys(
        data,
        "config",
        {"version", "users", "network", "activation", "os_upgrade", "containers"},
        {"version", "users", "activation", "containers"},
    )

    version = root.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        message = "version must be integer 1"
        raise provision_error(message)

    schema = config_schema if config_schema is not None else load_config_schema()
    validate_against_schema(data, schema, "config", schema)

    users, ssh_keys = load_users(root.get("users"))
    firewall_inbound = load_firewall_inbound(root.get("network"))

    lan_settings = load_network_settings(root.get("network"))
    host_network = load_host_network_settings(root.get("network"))

    os_upgrade_settings = None
    if root.get("os_upgrade") is not None:
        os_upgrade = require_allowed_keys(
            root.get("os_upgrade"), "os_upgrade", {"server_url"}, {"server_url"}
        )
        os_upgrade_settings = {
            "server_url": require_https_url(os_upgrade.get("server_url"), "os_upgrade.server_url")
        }

    containers = require_allowed_keys(
        root.get("containers"),
        "containers",
        {"container", "network", "volume", "build"},
        {"container"},
    )
    container_table = require_mapping(containers.get("container"), "containers.container")
    activation_policy = load_activation_policy(root.get("activation"), set(container_table))
    required_units = activation_policy["required"]

    result: dict[str, Any] = {
        "ssh_keys": ssh_keys,
        "users": users,
        "firewall_inbound": firewall_inbound,
        "lan_settings": lan_settings,
        "host_network": host_network,
        "os_upgrade": os_upgrade_settings,
        "required_units": required_units,
        "activation_policy": activation_policy,
        "containers": {
            "container": container_table,
            "network": containers.get("network"),
            "volume": containers.get("volume"),
            "build": containers.get("build"),
        },
    }

    return result
