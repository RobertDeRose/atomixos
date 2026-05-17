#!/usr/bin/env python3
import argparse
import base64
import email.policy
import errno
import hashlib
import html
import io
import ipaddress
import json
import os
import pwd
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import threading
import time
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


try:
    import tomllib
except ModuleNotFoundError:
    print("python3 with tomllib support is required", file=sys.stderr)
    sys.exit(1)


DEFAULT_CONFIG_DIR = Path("/data/config")
CONFIG_DIR_TOKEN = "${CONFIG_DIR}"  # noqa: S105
FILES_DIR_TOKEN = "${FILES_DIR}"  # noqa: S105
GZIP_MAGIC = b"\x1f\x8b"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
GZIP_BIN = os.environ.get("ATOMIXOS_GZIP", "gzip")
ZSTD_BIN = os.environ.get("ATOMIXOS_ZSTD", "zstd")
APP_RUNTIME_USER = "appsvc"
ROOTLESS_NETWORK_NAME = "pasta"
BOOTSTRAP_LAN_HOST = "172.20.30.1"
RUNTIME_METADATA_FILENAME = "quadlet-runtime.json"
FIREWALL_INBOUND_FILENAME = "firewall-inbound.json"
LAN_SETTINGS_FILENAME = "lan-settings.json"
OS_UPGRADE_FILENAME = "os-upgrade.json"
CONTAINER_SUFFIX = ".container"
NETWORK_SUFFIX = ".network"
VOLUME_SUFFIX = ".volume"
BUILD_SUFFIX = ".build"
QUADLET_SUFFIXES = {".build", ".container", ".image", ".kube", ".network", ".pod", ".volume"}
BOOTSTRAP_LOGO_PATH = Path(__file__).resolve().parent.parent / "share" / "atomixos" / "atomixos.png"
DEFAULT_LAN_GATEWAY_CIDR = "172.20.30.1/24"
DEFAULT_LAN_DHCP_START = "172.20.30.10"
DEFAULT_LAN_DHCP_END = "172.20.30.254"
DEFAULT_LAN_DOMAIN = "local"
DEFAULT_LAN_GATEWAY_ALIASES = ["atomixos"]
DEFAULT_LAN_HOSTNAME_PATTERN = ""
DEFAULT_NTP_SERVERS = ["time.cloudflare.com"]
SCHEMA_ENV = "ATOMIXOS_CONFIG_SCHEMA"
BOOTSTRAP_POST_RESPONSE_ENV = "ATOMIXOS_BOOTSTRAP_POST_RESPONSE"
BOOTSTRAP_ACTIVATION_ENV = "ATOMIXOS_BOOTSTRAP_ACTIVATION"
BOOTSTRAP_ACTIVATION_TIMEOUT_SECONDS = 300
MAX_REQUEST_BODY_BYTES = 50 * 1024 * 1024  # 50 MB
NONCE_TTL_SECONDS = int(os.environ.get("ATOMIXOS_NONCE_TTL", "300"))
SSH_KEYGEN_BIN = os.environ.get("ATOMIXOS_SSH_KEYGEN", "ssh-keygen")
AUTH_REQUIRED_MESSAGE = "authentication required: provide X-Atomicnix-Nonce and X-Atomicnix-Signature headers"
RESERVED_USERNAMES = {
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


class NonceStore:
    """Thread-safe in-memory store for short-lived authentication nonces."""

    def __init__(self, ttl: int = NONCE_TTL_SECONDS):
        self._ttl = ttl
        self._nonces: dict[str, float] = {}
        self._lock = threading.Lock()

    def issue(self) -> str:
        with self._lock:
            self._prune()
            nonce = secrets.token_urlsafe(32)
            self._nonces[nonce] = time.monotonic()
            return nonce

    def consume(self, nonce: str) -> bool:
        with self._lock:
            self._prune()
            issued_at = self._nonces.pop(nonce, None)
            if issued_at is None:
                return False
            return (time.monotonic() - issued_at) < self._ttl

    def _prune(self):
        now = time.monotonic()
        expired = [n for n, t in self._nonces.items() if (now - t) >= self._ttl]
        for n in expired:
            del self._nonces[n]


def reapply_signature_message(nonce: str, path: str, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    return f"atomixos-reapply-v1\nnonce:{nonce}\npath:{path}\nsha256:{digest}\n"


def verify_ssh_signature(message: str, signature_blob: bytes, allowed_keys_path: Path) -> bool:
    """Verify an SSH signature over a request-bound message.

    The allowed_keys_path should be a file in ssh allowed_signers format.
    Returns True if verification succeeds.
    """
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".sig", delete=False) as sig_file:
        sig_file.write(signature_blob)
        sig_path = sig_file.name

    try:
        result = subprocess.run(
            [
                SSH_KEYGEN_BIN, "-Y", "verify",
                "-f", str(allowed_keys_path),
                "-I", "atomixos-reapply",
                "-n", "atomixos-reapply",
                "-s", sig_path,
            ],
            input=message.encode(),
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    finally:
        Path(sig_path).unlink(missing_ok=True)


def build_allowed_signers(config_root: Path) -> Path | None:
    """Build a temporary allowed_signers file from active admin SSH keys.

    Returns the path to the temp file, or None if no keys exist.
    """
    admin_keys_path = config_root / "admin-signers"
    if not admin_keys_path.exists():
        return None

    keys = [line.strip() for line in admin_keys_path.read_text().splitlines() if line.strip()]
    if not keys:
        return None

    # allowed_signers format: <principal> <key>
    lines = [f"atomixos-reapply {key}" for key in keys]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".allowed_signers", delete=False) as tmp:
        tmp.write("\n".join(lines) + "\n")
        return Path(tmp.name)


class ProvisionError(RuntimeError):
    pass


def provision_error(message: str) -> ProvisionError:
    return ProvisionError(message)


def load_config_schema():
    candidates = []
    env_path = os.environ.get(SCHEMA_ENV)
    if env_path:
        candidates.append(Path(env_path))

    script_path = Path(__file__).resolve()
    candidates.extend(
        [
            script_path.parent.parent / "share" / "atomixos" / "config.schema.json",
            script_path.parent.parent / "schemas" / "config.schema.json",
        ]
    )

    for candidate in candidates:
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text())
            except json.JSONDecodeError as exc:
                message = f"invalid config schema in {candidate}: {exc}"
                raise provision_error(message) from exc

    searched = ", ".join(str(candidate) for candidate in candidates)
    message = f"unable to find config schema (checked: {searched})"
    raise provision_error(message)


CONFIG_SCHEMA = load_config_schema()


def resolve_schema_ref(schema: dict, ref: str):
    if not ref.startswith("#/"):
        message = f"unsupported schema ref: {ref}"
        raise provision_error(message)

    target = schema
    for part in ref[2:].split("/"):
        if not isinstance(target, dict) or part not in target:
            message = f"unresolvable schema ref: {ref}"
            raise provision_error(message)
        target = target[part]
    return target


def validate_schema_property_name(name: str, schema: dict, path: str):
    expected_type = schema.get("type")
    if expected_type == "string" and not isinstance(name, str):
        msg = f"expected string property name at {path}"
        raise provision_error(msg)
    pattern = schema.get("pattern")
    if pattern and not re.fullmatch(pattern, name):
        msg = f"invalid property name at {path}: {name!r}"
        raise provision_error(msg)


def validate_against_schema(value, schema: dict, path: str, root_schema: dict):
    if "$ref" in schema:
        validate_against_schema(value, resolve_schema_ref(root_schema, schema["$ref"]), path, root_schema)
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
        matches_type = False
        type_checks = {
            "object": lambda v: isinstance(v, dict),
            "array": lambda v: isinstance(v, list),
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
        }
        for allowed in allowed_types:
            check = type_checks.get(allowed)
            if check and check(value):
                matches_type = True
        if not matches_type:
            names = ", ".join(allowed_types)
            msg = f"expected {names} at {path}"
            raise provision_error(msg)

    if "enum" in schema and value not in schema["enum"]:
        msg = f"unexpected value at {path}: {value!r}"
        raise provision_error(msg)

    if isinstance(value, dict):
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


def validate_name(name: str) -> str:
    message = f"invalid quadlet unit name: {name!r}"
    if not name or "/" in name or "\x00" in name or "." in name or name in {".", ".."}:
        raise provision_error(message)
    for char in name:
        if not (char.isalnum() or char in {"_", "-"}):
            raise provision_error(message)
    return name


def validate_username(name: str) -> str:
    message = f"invalid user name: {name!r}"
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", name):
        raise provision_error(message)
    if name in RESERVED_USERNAMES:
        message = f"reserved user name: {name!r}"
        raise provision_error(message)
    return name


def require_mapping(value, path: str):
    if not isinstance(value, dict):
        message = f"expected table at {path}"
        raise provision_error(message)
    return value


def require_allowed_keys(value, path: str, allowed: set[str], required: set[str] | None = None):
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


def require_string(value, path: str):
    if not isinstance(value, str) or not value.strip():
        message = f"expected non-empty string at {path}"
        raise provision_error(message)
    return value.strip()


def require_string_list(value, path: str):
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


def require_optional_string_list(value, path: str):
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


def require_ntp_server_list(value, path: str):
    servers = require_string_list(value, path)
    for idx, server in enumerate(servers):
        if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in server):
            message = f"invalid NTP server at {path}[{idx}]: whitespace and control characters are not allowed"
            raise provision_error(message)
    return servers


def require_bool(value, path: str):
    if not isinstance(value, bool):
        message = f"expected boolean at {path}"
        raise provision_error(message)
    return value


def require_port_list(value, path: str):
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


def require_dns_name(value, path: str):
    name = require_string(value, path).lower().rstrip(".")
    if not name:
        message = f"expected non-empty string at {path}"
        raise provision_error(message)

    labels = name.split(".")
    invalid_name_message = f"invalid DNS name at {path}: {value!r}"
    for label in labels:
        if not label or len(label) > 63:
            raise provision_error(invalid_name_message)
        if not label[0].isalnum() or not label[-1].isalnum():
            raise provision_error(invalid_name_message)
        for char in label:
            if not (char.isalnum() or char == "-"):
                raise provision_error(invalid_name_message)
    return name


def load_lan_settings(lan_value, path: str = "lan"):
    if lan_value is None:
        lan_value = {}

    lan = require_allowed_keys(
        lan_value,
        path,
        {"gateway_cidr", "dhcp_start", "dhcp_end", "domain", "hostname_pattern", "gateway_aliases"},
    )

    gateway_cidr = require_string(lan.get("gateway_cidr", DEFAULT_LAN_GATEWAY_CIDR), f"{path}.gateway_cidr")
    try:
        gateway = ipaddress.IPv4Interface(gateway_cidr)
    except ValueError as exc:
        message = f"invalid IPv4 CIDR at {path}.gateway_cidr: {gateway_cidr}"
        raise provision_error(message) from exc
    if gateway.network.prefixlen != 24:
        message = f"{path}.gateway_cidr must use a /24 subnet"
        raise provision_error(message)

    dhcp_start_raw = require_string(lan.get("dhcp_start", DEFAULT_LAN_DHCP_START), f"{path}.dhcp_start")
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
    hostname_pattern = require_string(
        lan.get("hostname_pattern", DEFAULT_LAN_HOSTNAME_PATTERN) or DEFAULT_LAN_HOSTNAME_PATTERN,
        f"{path}.hostname_pattern",
    ) if lan.get("hostname_pattern") not in (None, "") else DEFAULT_LAN_HOSTNAME_PATTERN
    if hostname_pattern:
        if "{mac}" not in hostname_pattern:
            message = f"{path}.hostname_pattern must include {{mac}}"
            raise provision_error(message)
        pattern_probe = hostname_pattern.replace("{mac}", "001122334455")
        require_dns_name(pattern_probe, f"{path}.hostname_pattern")

    gateway_aliases = require_optional_string_list(lan.get("gateway_aliases"), f"{path}.gateway_aliases")
    if not gateway_aliases:
        gateway_aliases = list(DEFAULT_LAN_GATEWAY_ALIASES)
    gateway_aliases = [require_dns_name(alias, f"{path}.gateway_aliases") for alias in gateway_aliases]

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


def load_users(users_value):
    users = require_mapping(users_value, "users")
    normalized = {}
    admin_keys = []

    for username, raw_user in users.items():
        validate_username(username)
        user = require_allowed_keys(raw_user, f"users.{username}", {"isAdmin", "ssh_key"})
        is_admin = require_bool(user.get("isAdmin", False), f"users.{username}.isAdmin")
        ssh_key_raw = user.get("ssh_key", "")
        if not isinstance(ssh_key_raw, str):
            message = f"expected string at users.{username}.ssh_key"
            raise provision_error(message)
        ssh_key = ssh_key_raw.strip()
        normalized[username] = {
            "isAdmin": is_admin,
            "ssh_key": ssh_key,
        }
        if is_admin and ssh_key:
            admin_keys.append(ssh_key)

    if not admin_keys:
        message = "users must define at least one admin user with a non-empty ssh_key"
        raise provision_error(message)

    return normalized, admin_keys


def load_network_settings(network_value):
    if network_value is None:
        network_value = {}
    network = require_allowed_keys(
        network_value,
        "network",
        {"dns_servers", "dns_search_domains", "default_gateway", "interfaces", "dnsmasq", "ntp", "firewall"},
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

    if "enable" in dnsmasq_settings and not require_bool(dnsmasq_settings["enable"], "network.dnsmasq.enable"):
        message = "network.dnsmasq.enable must remain true; disabling LAN DHCP/DNS is not supported"
        raise provision_error(message)
    if "interface" in dnsmasq_settings:
        interface = require_string(dnsmasq_settings["interface"], "network.dnsmasq.interface")
        if interface != "eth1":
            message = "network.dnsmasq.interface must be eth1"
            raise provision_error(message)

    lan_settings = load_lan_settings(dnsmasq_settings, "network.dnsmasq")
    ntp = require_allowed_keys(network.get("ntp", {}), "network.ntp", {"servers"})
    lan_settings["ntp_servers"] = require_ntp_server_list(
        ntp.get("servers", DEFAULT_NTP_SERVERS),
        "network.ntp.servers",
    )
    return lan_settings


def load_firewall_inbound(network_value):
    if network_value is None:
        network_value = {}
    network = require_allowed_keys(
        network_value,
        "network",
        {"dns_servers", "dns_search_domains", "default_gateway", "interfaces", "dnsmasq", "ntp", "firewall"},
    )
    firewall = network.get("firewall", {})
    firewall = require_allowed_keys(firewall, "network.firewall", {"inbound"})
    inbound_value = firewall.get("inbound", {})
    inbound = require_allowed_keys(inbound_value, "network.firewall.inbound", {"wan", "lan"})

    def normalize_firewall_scope(scope_value, scope_path: str):
        if scope_value is None:
            return {}
        scope = require_allowed_keys(scope_value, scope_path, {"tcp", "udp"})
        normalized = {}
        if "tcp" in scope:
            tcp_ports = require_port_list(scope.get("tcp"), f"{scope_path}.tcp")
            if tcp_ports:
                normalized["tcp"] = tcp_ports
        if "udp" in scope:
            udp_ports = require_port_list(scope.get("udp"), f"{scope_path}.udp")
            if udp_ports:
                normalized["udp"] = udp_ports
        return normalized

    firewall_inbound = {}
    wan_scope = normalize_firewall_scope(inbound.get("wan"), "network.firewall.inbound.wan")
    if wan_scope:
        firewall_inbound["wan"] = wan_scope
    lan_scope = normalize_firewall_scope(inbound.get("lan"), "network.firewall.inbound.lan")
    if lan_scope:
        firewall_inbound["lan"] = lan_scope
    return firewall_inbound


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def maybe_chown_user(path: Path, username: str):
    try:
        user = pwd.getpwnam(username)
    except KeyError:
        return

    os.chown(path, user.pw_uid, user.pw_gid)


def format_scalar(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value
    message = f"unsupported scalar value type: {type(value).__name__}"
    raise provision_error(message)


def substitute_tokens(value: str, config_root: Path):
    return value.replace(CONFIG_DIR_TOKEN, str(config_root)).replace(
        FILES_DIR_TOKEN, str(config_root / "files")
    )


def normalize_directives(directives_table: dict, path: str):
    normalized = {}
    for key, raw_value in directives_table.items():
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        if not values:
            continue

        normalized_values = []
        for idx, value in enumerate(values):
            item_path = f"{path}.{key}[{idx}]" if isinstance(raw_value, list) else f"{path}.{key}"
            if isinstance(value, (list, dict)):
                message = f"expected scalar value at {item_path}"
                raise provision_error(message)
            normalized_values.append(value)
        normalized[key] = normalized_values
    return normalized


def rewrite_rootless_publish_port(value: str, container_name: str, warnings: list[str]):
    if value.startswith("["):
        host_end = value.find("]")
        if host_end == -1 or host_end + 1 >= len(value) or value[host_end + 1] != ":":
            return value
        bind_host = value[: host_end + 1]
        remainder = value[host_end + 2 :]
    else:
        parts = value.split(":")
        if len(parts) == 2:
            return f"127.0.0.1:{value}"
        if len(parts) < 3:
            return value
        bind_host = parts[0]
        remainder = ":".join(parts[1:])

    if bind_host in {"127.0.0.1", "127.0.1.1"}:
        return value
    if bind_host in {"localhost", "::1", "[::1]"}:
        return f"127.0.0.1:{remainder}"

    warnings.append(
        f"container.{container_name}.Container.PublishPort rewrote non-loopback bind {value!r} to 127.0.0.1"
    )
    return f"127.0.0.1:{remainder}"


def render_section(section_name: str, directives: dict[str, list], config_root: Path):
    lines = [f"[{section_name}]"]
    for key, values in directives.items():
        for value in values:
            rendered_value = substitute_tokens(value, config_root) if isinstance(value, str) else value
            lines.append(f"{key}={format_scalar(rendered_value)}")
    lines.append("")
    return lines


def render_containers(container_table: dict, config_root: Path):
    rendered = {}
    runtime_units = []
    warnings = []

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

        if privileged:
            if "Network" in container_directives and container_directives["Network"] != ["host"]:
                warnings.append(
                    f"container.{container_name}.Container.Network overridden to host for privileged container"
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
                    port_value = require_string(value, f"{container_path}.Container.PublishPort[{idx}]")
                    rewritten_ports.append(rewrite_rootless_publish_port(port_value, container_name, warnings))
                container_directives["PublishPort"] = rewritten_ports
            runtime_mode = "rootless"

        lines = []
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


def render_networks(network_table: dict, config_root: Path):
    rendered = {}
    runtime_units = []
    if not network_table:
        return rendered, runtime_units

    for network_name, raw_sections in network_table.items():
        validate_name(network_name)
        network_path = f"network.{network_name}"
        sections = require_allowed_keys(
            raw_sections,
            network_path,
            {"Network"},
            {"Network"},
        )
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


def render_volumes(volume_table: dict, config_root: Path):
    rendered = {}
    runtime_units = []
    if not volume_table:
        return rendered, runtime_units

    for volume_name, raw_sections in volume_table.items():
        validate_name(volume_name)
        volume_path = f"volume.{volume_name}"
        sections = require_allowed_keys(
            raw_sections,
            volume_path,
            {"Volume"},
            {"Volume"},
        )
        volume_directives = normalize_directives(
            require_mapping(sections.get("Volume"), f"{volume_path}.Volume"),
            f"{volume_path}.Volume",
        )

        lines = render_section("Volume", volume_directives, config_root)
        filename = f"{volume_name}{VOLUME_SUFFIX}"
        rendered[filename] = "\n".join(lines).rstrip() + "\n"
        runtime_units.append(
            {
                "name": volume_name,
                "filename": filename,
                "service": f"{volume_name}-volume.service",
                "mode": "rootful",
            }
        )

    return rendered, runtime_units


def render_builds(build_table: dict, config_root: Path):
    rendered = {}
    runtime_units = []
    if not build_table:
        return rendered, runtime_units

    for build_name, raw_sections in build_table.items():
        validate_name(build_name)
        build_path = f"build.{build_name}"
        sections = require_allowed_keys(
            raw_sections,
            build_path,
            {"Build"},
            {"Build"},
        )
        build_directives = normalize_directives(
            require_mapping(sections.get("Build"), f"{build_path}.Build"),
            f"{build_path}.Build",
        )

        lines = render_section("Build", build_directives, config_root)
        filename = f"{build_name}{BUILD_SUFFIX}"
        rendered[filename] = "\n".join(lines).rstrip() + "\n"
        runtime_units.append(
            {
                "name": build_name,
                "filename": filename,
                "service": f"{build_name}-build.service",
                "mode": "rootful",
            }
        )

    return rendered, runtime_units


def load_config(config_path: Path, config_root: Path = DEFAULT_CONFIG_DIR):
    try:
        data = tomllib.loads(config_path.read_text())
    except tomllib.TOMLDecodeError as exc:
        message = f"invalid TOML in {config_path}: {exc}"
        raise provision_error(message) from exc

    validate_against_schema(data, CONFIG_SCHEMA, "config", CONFIG_SCHEMA)

    root = require_allowed_keys(
        data,
        "config",
        {"version", "users", "network", "activation", "os_upgrade", "containers"},
        {"version", "users", "activation", "containers"},
    )

    version = root.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != 2:
        message = "version must be integer 2"
        raise provision_error(message)

    users, ssh_keys = load_users(root.get("users"))
    firewall_inbound = load_firewall_inbound(root.get("network"))

    activation = require_allowed_keys(root.get("activation"), "activation", {"required"}, {"required"})
    required_units = require_string_list(activation.get("required"), "activation.required")

    lan_settings = load_network_settings(root.get("network"))

    os_upgrade_settings = None
    if root.get("os_upgrade") is not None:
        os_upgrade = require_allowed_keys(root.get("os_upgrade"), "os_upgrade", {"server_url"}, {"server_url"})
        os_upgrade_settings = {
            "server_url": require_string(os_upgrade.get("server_url"), "os_upgrade.server_url")
        }

    containers = require_allowed_keys(
        root.get("containers"),
        "containers",
        {"container", "network", "volume", "build"},
        {"container"},
    )
    container = require_mapping(containers.get("container"), "containers.container")
    rendered_units, runtime_units, warnings = render_containers(container, config_root)
    if not rendered_units:
        message = "config.toml must define at least one Quadlet unit"
        raise provision_error(message)

    network_table = containers.get("network")
    if network_table is not None:
        rendered_networks, network_runtime = render_networks(
            require_mapping(network_table, "containers.network"), config_root
        )
        rendered_units.update(rendered_networks)
        runtime_units.extend(network_runtime)

    volume_table = containers.get("volume")
    if volume_table is not None:
        rendered_volumes, volume_runtime = render_volumes(
            require_mapping(volume_table, "containers.volume"), config_root
        )
        rendered_units.update(rendered_volumes)
        runtime_units.extend(volume_runtime)

    build_table = containers.get("build")
    if build_table is not None:
        rendered_builds, build_runtime = render_builds(
            require_mapping(build_table, "containers.build"), config_root
        )
        rendered_units.update(rendered_builds)
        runtime_units.extend(build_runtime)

    for unit in required_units:
        if unit not in container:
            message = f"activation.required references unknown unit: {unit}"
            raise provision_error(message)

    return {
        "ssh_keys": ssh_keys,
        "users": users,
        "firewall_inbound": firewall_inbound,
        "lan_settings": lan_settings,
        "os_upgrade": os_upgrade_settings,
        "required_units": required_units,
        "rendered_units": rendered_units,
        "runtime": {
            "app_user": APP_RUNTIME_USER,
            "rootless_network": ROOTLESS_NETWORK_NAME,
            "units": runtime_units,
        },
        "warnings": warnings,
    }


def detect_bundle_kind(source_bytes: bytes, filename: str = ""):
    lowered = filename.lower()
    if lowered.endswith((".tar.gz", ".tgz")) or source_bytes.startswith(GZIP_MAGIC):
        return "tar.gz"
    if lowered.endswith((".tar.zst", ".tar.zstd", ".tzst")) or source_bytes.startswith(ZSTD_MAGIC):
        return "tar.zst"
    return None


def validate_bundle_member(name: str):
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or name == "":
        message = f"invalid bundle member path: {name!r}"
        raise provision_error(message)


def generated_required_units(quadlet: str):
    snippet = quadlet.strip()
    if not snippet:
        message = "container TOML snippet is required"
        raise provision_error(message)

    try:
        parsed = tomllib.loads(snippet)
    except tomllib.TOMLDecodeError as exc:
        message = f"invalid container TOML snippet: {exc}"
        raise provision_error(message) from exc

    container = parsed.get("container")
    if not isinstance(container, dict) or not container:
        message = "container TOML snippet must define at least one [container.<name>] table"
        raise provision_error(message)

    return [validate_name(name) for name in container]


def generated_extra_users(ssh_keys: list[str]):
    blocks = []
    for index, ssh_key in enumerate(ssh_keys, start=2):
        blocks.append(
            textwrap.dedent(
                f"""
                [users.admin{index}]
                isAdmin = true
                ssh_key = {json.dumps(ssh_key)}
                """
            ).strip()
        )
    return "\n\n".join(blocks)


def uploaded_config_text(payload: bytes, filename: str):
    if detect_bundle_kind(payload, filename) is not None:
        return ""
    return payload.decode("utf-8", errors="replace")


def extract_bundle_archive(source_bytes: bytes, filename: str, destination: Path):
    bundle_kind = detect_bundle_kind(source_bytes, filename)
    if bundle_kind == "tar.gz":
        try:
            decompressed = subprocess.run(
                [GZIP_BIN, "-dc"],
                input=source_bytes,
                capture_output=True,
                check=True,
            ).stdout
        except FileNotFoundError as exc:
            message = "gzip is required to import .tar.gz bundles"
            raise provision_error(message) from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace").strip()
            detail = f": {stderr}" if stderr else ""
            message = f"failed to decompress .tar.gz bundle{detail}"
            raise provision_error(message) from exc
    elif bundle_kind == "tar.zst":
        try:
            decompressed = subprocess.run(
                [ZSTD_BIN, "-dcq"],
                input=source_bytes,
                capture_output=True,
                check=True,
            ).stdout
        except FileNotFoundError as exc:
            message = "zstd is required to import .tar.zst bundles"
            raise provision_error(message) from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace").strip()
            detail = f": {stderr}" if stderr else ""
            message = f"failed to decompress .tar.zst bundle{detail}"
            raise provision_error(message) from exc
    else:
        message = "supported bundle formats are .tar.gz, .tgz, .tar.zst, .tar.zstd, and .tzst"
        raise provision_error(message)

    with tarfile.open(fileobj=io.BytesIO(decompressed), mode="r:") as archive:
        for member in archive.getmembers():
            validate_bundle_member(member.name)
            if member.name == ".":
                if member.isdir():
                    continue
                message = "bundle member '.' must be a directory"
                raise provision_error(message)
            target = destination / member.name
            if member.isdir():
                ensure_dir(target)
                target.chmod(0o755)
                continue
            if not member.isfile():
                message = f"unsupported bundle member type: {member.name}"
                raise provision_error(message)

            ensure_dir(target.parent)
            extracted = archive.extractfile(member)
            if extracted is None:
                message = f"failed to read bundle member: {member.name}"
                raise provision_error(message)
            with extracted, target.open("wb") as output:
                shutil.copyfileobj(extracted, output)
            target.chmod(0o644)


def validate_bundle_layout(bundle_root: Path):
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


def prepare_bundle_from_bytes(source_bytes: bytes, filename: str = ""):
    tmpdir = tempfile.TemporaryDirectory()
    bundle_root = Path(tmpdir.name)
    extract_bundle_archive(source_bytes, filename, bundle_root)
    validate_bundle_layout(bundle_root)
    return tmpdir, bundle_root / "config.toml", bundle_root / "files"


def prepare_source_path(source_path: Path):
    if source_path.suffix == ".toml":
        return None, source_path, None

    source_bytes = source_path.read_bytes()
    bundle_kind = detect_bundle_kind(source_bytes, source_path.name)
    if bundle_kind is None:
        message = "supported import inputs are config.toml, .tar.gz/.tgz, and .tar.zst/.tar.zstd/.tzst"
        raise provision_error(message)
    return prepare_bundle_from_bytes(source_bytes, source_path.name)


def prepare_source_bytes(source_bytes: bytes, filename: str = ""):
    bundle_kind = detect_bundle_kind(source_bytes, filename)
    if bundle_kind is not None:
        return prepare_bundle_from_bytes(source_bytes, filename)

    tmpdir = tempfile.TemporaryDirectory()
    config_path = Path(tmpdir.name) / "config.toml"
    config_path.write_bytes(source_bytes)
    return tmpdir, config_path, None


def copy_bundle_files(files_source: Path | None, config_root: Path):
    target = config_root / "files"
    shutil.rmtree(target, ignore_errors=True)
    if files_source is None or not files_source.exists():
        return

    for source in files_source.rglob("*"):
        relative = source.relative_to(files_source)
        destination = target / relative
        if source.is_dir():
            ensure_dir(destination)
            destination.chmod(0o755)
            continue

        ensure_dir(destination.parent)
        shutil.copyfile(source, destination)
        destination.chmod(0o644)


def write_imported_state(parsed: dict, prepared_config: Path, prepared_files: Path | None, config_root: Path):
    ensure_dir(config_root)
    ensure_dir(config_root / "ssh-authorized-keys")
    ensure_dir(config_root / "quadlet")

    imported_path = config_root / "config.toml"
    shutil.copyfile(prepared_config, imported_path)
    imported_path.chmod(0o600)

    users_path = config_root / "users.json"
    users_path.write_text(json.dumps(parsed["users"], indent=2) + "\n")
    users_path.chmod(0o600)

    ssh_dir = config_root / "ssh-authorized-keys"
    desired_key_files = set(parsed["users"].keys())
    for existing_key_file in ssh_dir.iterdir():
        if existing_key_file.is_file() and existing_key_file.name not in desired_key_files:
            existing_key_file.unlink()

    signers_path = config_root / "admin-signers"
    signers_path.write_text("\n".join(parsed["ssh_keys"]) + "\n")
    signers_path.chmod(0o600)

    for username, user in parsed["users"].items():
        user_ssh_path = ssh_dir / username
        ssh_key = user["ssh_key"]
        if ssh_key:
            user_ssh_path.write_text(ssh_key + "\n")
            user_ssh_path.chmod(0o600)
            maybe_chown_user(user_ssh_path, username)
        else:
            user_ssh_path.unlink(missing_ok=True)

    health_path = config_root / "health-required.json"
    health_path.write_text(json.dumps(parsed["required_units"], indent=2) + "\n")
    health_path.chmod(0o600)

    firewall_path = config_root / FIREWALL_INBOUND_FILENAME
    firewall_path.write_text(json.dumps(parsed["firewall_inbound"], indent=2) + "\n")
    firewall_path.chmod(0o600)

    lan_settings_path = config_root / LAN_SETTINGS_FILENAME
    lan_settings_path.write_text(json.dumps(parsed["lan_settings"], indent=2) + "\n")
    lan_settings_path.chmod(0o600)

    os_upgrade_path = config_root / OS_UPGRADE_FILENAME
    if parsed["os_upgrade"] is None:
        os_upgrade_path.unlink(missing_ok=True)
    else:
        os_upgrade_path.write_text(json.dumps(parsed["os_upgrade"], indent=2) + "\n")
        os_upgrade_path.chmod(0o600)

    runtime_path = config_root / RUNTIME_METADATA_FILENAME
    runtime_path.write_text(json.dumps(parsed["runtime"], indent=2) + "\n")
    runtime_path.chmod(0o600)

    quadlet_dir = config_root / "quadlet"
    for existing in quadlet_dir.iterdir():
        if existing.is_file():
            existing.unlink()
    for filename, content in parsed["rendered_units"].items():
        unit_path = quadlet_dir / filename
        unit_path.write_text(content)
        unit_path.chmod(0o644)

    copy_bundle_files(prepared_files, config_root)


def carry_forward_managed_state(previous_root: Path, candidate_root: Path) -> None:
    previous_state = previous_root / "managed-users.json"
    if not previous_state.exists():
        return
    target_state = candidate_root / "managed-users.json"
    shutil.copyfile(previous_state, target_state)
    target_state.chmod(0o600)


def read_managed_state(config_root: Path) -> set[str]:
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
    state_path = config_root / "managed-users.json"
    state_path.write_text(json.dumps(sorted(names), indent=2) + "\n")
    state_path.chmod(0o600)


def load_runtime_metadata(config_root: Path):
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


def import_config(config_path: Path, config_root: Path):
    temp_bundle, prepared_config, prepared_files = prepare_source_path(config_path)
    try:
        parsed = load_config(prepared_config, config_root)
        write_imported_state(parsed, prepared_config, prepared_files, config_root)
        return parsed["warnings"]
    finally:
        if temp_bundle is not None:
            temp_bundle.cleanup()


CANDIDATE_SUFFIX = "-candidate"
ROLLBACK_SUFFIX = "-rollback"
PROMOTION_MARKER = ".atomixos-promotion-pending"


def promotion_marker_path(config_root: Path) -> Path:
    return config_root.parent / f"{config_root.name}{PROMOTION_MARKER}"


def atomic_import_config(config_path: Path, config_root: Path):
    """Import config atomically with rollback preservation.

    For fresh provisioning (config_root doesn't exist or has no config.toml),
    writes directly. For re-apply, renders into a candidate directory and
    promotes via rename, preserving the previous state for rollback.
    """
    temp_bundle, prepared_config, prepared_files = prepare_source_path(config_path)
    try:
        recover_config_root(config_root)
        is_reapply = (config_root / "config.toml").exists()

        if not is_reapply:
            # Fresh provisioning: write directly.
            parsed = load_config(prepared_config, config_root)
            write_imported_state(parsed, prepared_config, prepared_files, config_root)
            return parsed["warnings"]

        # Re-apply: render into candidate, then promote atomically.
        candidate_root = config_root.parent / (config_root.name + CANDIDATE_SUFFIX)
        rollback_root = config_root.parent / (config_root.name + ROLLBACK_SUFFIX)

        # Clean stale candidate from a previous failed attempt.
        if candidate_root.exists():
            shutil.rmtree(candidate_root)

        candidate_root.mkdir(parents=True, exist_ok=True)

        # Validate and render into candidate directory.
        parsed = load_config(prepared_config, config_root)
        write_imported_state(parsed, prepared_config, prepared_files, candidate_root)
        carry_forward_managed_state(config_root, candidate_root)

        # Atomic promotion: active → rollback, candidate → active.
        # Remove stale rollback from a previous successful apply.
        if rollback_root.exists():
            shutil.rmtree(rollback_root)

        # Step 1: move active to rollback (preserves previous state).
        promotion_marker_path(config_root).write_text("pending\n")
        config_root.rename(rollback_root)
        # Step 2: move candidate to active.
        candidate_root.rename(config_root)
        promotion_marker_path(config_root).unlink(missing_ok=True)

        return parsed["warnings"]
    finally:
        if temp_bundle is not None:
            temp_bundle.cleanup()


def cleanup_rollback(config_root: Path):
    """Remove rollback state after successful activation."""
    rollback_root = config_root.parent / (config_root.name + ROLLBACK_SUFFIX)
    if rollback_root.exists():
        shutil.rmtree(rollback_root)
    promotion_marker_path(config_root).unlink(missing_ok=True)


def recover_config_root(config_root: Path) -> None:
    """Recover from an interrupted active→rollback, candidate→active promotion."""
    rollback_root = config_root.parent / (config_root.name + ROLLBACK_SUFFIX)
    candidate_root = config_root.parent / (config_root.name + CANDIDATE_SUFFIX)
    marker_path = promotion_marker_path(config_root)
    if marker_path.exists() and rollback_root.exists():
        if config_root.exists():
            shutil.rmtree(config_root)
        rollback_root.rename(config_root)
        if candidate_root.exists():
            shutil.rmtree(candidate_root)
        marker_path.unlink(missing_ok=True)
        return
    if marker_path.exists() and not rollback_root.exists():
        marker_path.unlink(missing_ok=True)
        return
    if (config_root / "config.toml").exists():
        return
    if candidate_root.exists():
        candidate_root.rename(config_root)
        return
    if rollback_root.exists():
        rollback_root.rename(config_root)


def restore_rollback(config_root: Path) -> bool:
    """Restore previous config from rollback. Returns True if restored."""
    rollback_root = config_root.parent / (config_root.name + ROLLBACK_SUFFIX)
    marker_path = promotion_marker_path(config_root)
    if not rollback_root.exists():
        marker_path.unlink(missing_ok=True)
        return False

    failed_managed = read_managed_state(config_root)
    rollback_managed = read_managed_state(rollback_root)

    # Remove the failed active config.
    if config_root.exists():
        shutil.rmtree(config_root)
    rollback_root.rename(config_root)
    merged_managed = rollback_managed | failed_managed
    if merged_managed:
        write_managed_state(config_root, merged_managed)
    marker_path.unlink(missing_ok=True)
    return True


def validate_config_source(source_path: Path):
    temp_bundle, prepared_config, _prepared_files = prepare_source_path(source_path)
    try:
        parsed = load_config(prepared_config)
        return parsed["warnings"]
    finally:
        if temp_bundle is not None:
            temp_bundle.cleanup()


def sync_quadlet_units(config_root: Path, rootful_target: Path, rootless_target: Path | None = None):
    source = config_root / "quadlet"
    metadata = load_runtime_metadata(config_root)
    units_by_mode = {"rootful": set(), "rootless": set()}
    for unit in metadata["units"]:
        if not isinstance(unit, dict):
            message = "invalid runtime unit entry"
            raise provision_error(message)
        filename = unit.get("filename")
        mode = unit.get("mode")
        if not isinstance(filename, str) or mode not in units_by_mode:
            message = "invalid runtime unit metadata"
            raise provision_error(message)
        units_by_mode[mode].add(filename)

    ensure_dir(rootful_target)
    existing_rootful = {
        path.name for path in rootful_target.iterdir() if path.is_file() and path.suffix in QUADLET_SUFFIXES
    }
    desired_rootful = units_by_mode["rootful"]

    for filename in desired_rootful:
        unit_file = source / filename
        shutil.copyfile(unit_file, rootful_target / filename)
        (rootful_target / filename).chmod(0o644)

    for stale in existing_rootful - desired_rootful:
        (rootful_target / stale).unlink()

    if rootless_target is None:
        if units_by_mode["rootless"]:
            message = "rootless target path is required when rootless units are present"
            raise provision_error(message)
        return

    ensure_dir(rootless_target)
    existing_rootless = {
        path.name for path in rootless_target.iterdir() if path.is_file() and path.suffix in QUADLET_SUFFIXES
    }
    desired_rootless = units_by_mode["rootless"]

    for filename in desired_rootless:
        unit_file = source / filename
        shutil.copyfile(unit_file, rootless_target / filename)
        (rootless_target / filename).chmod(0o644)

    for stale in existing_rootless - desired_rootless:
        (rootless_target / stale).unlink()


BOOTSTRAP_HTML = """<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <title>AtomixOS Bootstrap</title>
    <style>
      :root {{
        color-scheme: dark;
        --bg: #06102a;
        --panel: rgba(11, 26, 58, 0.88);
        --panel-border: rgba(93, 121, 168, 0.34);
        --fg: #d4e6ff;
        --muted: #c3dbff;
        --link: #61b3ff;
        --accent: #4ea3ff;
        --accent-strong: #2f7fe0;
        --input: rgba(10, 22, 50, 0.9);
        --input-border: rgba(124, 183, 255, 0.28);
        --shadow: rgba(0, 0, 0, 0.35);
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
        color: var(--fg);
        background:
          radial-gradient(circle at 16% 8%, rgba(76, 146, 255, 0.2), transparent 36%),
          radial-gradient(circle at 86% 0%, rgba(50, 107, 206, 0.2), transparent 30%),
          var(--bg);
      }}
      main {{
        max-width: 60rem;
        margin: 0 auto;
        padding: 1.5rem 1rem 2rem;
      }}
      .hero {{
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        gap: 0.85rem;
        margin-bottom: 1.5rem;
      }}
      .hero-mark {{
        width: min(19rem, 68vw);
        height: auto;
        filter: drop-shadow(0 12px 28px rgba(0, 0, 0, 0.34));
      }}
      .hero h1 {{
        margin: 0;
        font-size: clamp(1.8rem, 4vw, 2.7rem);
        letter-spacing: 0.02em;
        color: #e7f3ff;
      }}
      .hero p {{
        margin: 0;
        max-width: 44rem;
        color: var(--muted);
        line-height: 1.6;
      }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
        gap: 1rem;
      }}
      .panel {{
        background: var(--panel);
        border: 1px solid var(--panel-border);
        border-radius: 14px;
        box-shadow: 0 18px 54px var(--shadow);
        padding: 1rem;
        backdrop-filter: blur(8px);
      }}
      .panel h2 {{
        margin: 0 0 0.35rem;
        font-size: 1.15rem;
        color: #e7f3ff;
      }}
      .panel p {{
        margin: 0 0 0.75rem;
        color: var(--muted);
        line-height: 1.5;
      }}
      label {{
        display: block;
        margin-top: 0.9rem;
        margin-bottom: 0.35rem;
        color: #e7f3ff;
        font-weight: 600;
      }}
      input[type=file], textarea {{
        width: 100%;
        border-radius: 10px;
        border: 1px solid var(--input-border);
        background: var(--input);
        color: var(--fg);
        padding: 0.8rem 0.9rem;
        font: inherit;
      }}
      textarea {{
        min-height: 18rem;
        resize: vertical;
        font-family: ui-monospace, SFMono-Regular, SFMono-Regular, Menlo, Consolas, monospace;
      }}
      .short {{ min-height: 6rem; }}
      .medium {{ min-height: 8rem; }}
      button {{
        margin-top: 1rem;
        border: 1px solid rgba(124, 183, 255, 0.45);
        border-radius: 999px;
        background: linear-gradient(180deg, var(--accent), var(--accent-strong));
        color: #f4f9ff;
        cursor: pointer;
        font: inherit;
        font-weight: 700;
        padding: 0.75rem 1.15rem;
        box-shadow: 0 10px 24px rgba(26, 73, 150, 0.35);
      }}
      button:hover, button:focus-visible {{
        filter: brightness(1.08);
      }}
      a {{
        color: var(--link);
        text-underline-offset: 0.14em;
      }}
      code {{
        color: #c6defe;
        background: rgba(33, 70, 130, 0.34);
        border: 1px solid rgba(86, 141, 226, 0.32);
        border-radius: 0.4rem;
        padding: 0.08rem 0.35rem;
      }}
      .message {{
        margin-top: 1rem;
        background: rgba(13, 26, 56, 0.88);
        border: 1px solid rgba(86, 141, 226, 0.28);
        border-radius: 12px;
        padding: 0.9rem 1rem;
      }}
      .message p {{ margin: 0; }}
      .message-actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        margin-top: 0.75rem;
      }}
      @media (max-width: 640px) {{
        main {{ padding: 1rem 0.75rem 1.5rem; }}
        .panel {{ padding: 0.85rem; }}
      }}
    </style>
    <script>
      function downloadAppliedConfig() {{
        const textarea = document.querySelector('textarea[name="config"]');
        if (!textarea) {{
          return;
        }}

        const blob = new Blob([textarea.value], {{ type: 'text/plain;charset=utf-8' }});
        const href = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = href;
        link.download = 'config.toml';
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(href);
      }}
    </script>
  </head>
  <body>
    <main>
      <section class=\"hero\">
        <img class=\"hero-mark\" src=\"/assets/atomixos.png\" alt=\"AtomixOS logo\">
        <h1>Bootstrap Console</h1>
        <p>
          Import an existing <code>config.toml</code>, <code>config.tar.gz</code>,
          <code>config.tar.zst</code>, or <code>config.tar.zstd</code> bundle, or build a fresh
          configuration with the guided form below.
        </p>
      </section>
      <section class=\"grid\">
        <form class=\"panel\" method=\"post\" action=\"/apply\" enctype=\"multipart/form-data\">
          <h2>Apply Existing Configuration</h2>
          <p>Upload a prepared config or paste a plain <code>config.toml</code> payload.</p>
          <label>Config file or bundle</label>
          <input
            type=\"file\"
            name=\"config_file\"
          >
          <label>config.toml</label>
          <textarea name=\"config\">{config_text}</textarea>
          <button type=\"submit\">Apply configuration</button>
        </form>
        <form class=\"panel\" method=\"post\" action=\"/generate\">
          <h2>Generate New Configuration</h2>
          <p>Build a valid AtomixOS bootstrap config for operator access and provisioned containers.</p>
          <label>Admin SSH keys (one per line)</label>
          <textarea class=\"medium\" name=\"ssh_keys\"></textarea>
          <label>WAN TCP ports (one per line)</label>
          <textarea class=\"short\" name=\"wan_tcp\">443</textarea>
          <label>WAN UDP ports (one per line)</label>
          <textarea class=\"short\" name=\"wan_udp\">1194</textarea>
          <label>LAN TCP ports (one per line, blank keeps LAN open)</label>
          <textarea class=\"short\" name=\"lan_tcp\"></textarea>
          <label>LAN UDP ports (one per line, blank keeps LAN open)</label>
          <textarea class=\"short\" name=\"lan_udp\"></textarea>
          <label>Update server URL (blank disables OTA polling)</label>
          <textarea class=\"short\" name=\"os_upgrade_server_url\"></textarea>
          <label>LAN gateway CIDR</label>
          <textarea class=\"short\" name=\"gateway_cidr\">172.20.30.1/24</textarea>
          <label>LAN DHCP start</label>
          <textarea class=\"short\" name=\"dhcp_start\">172.20.30.10</textarea>
          <label>LAN DHCP end</label>
          <textarea class=\"short\" name=\"dhcp_end\">172.20.30.254</textarea>
          <label>LAN default domain</label>
          <textarea class=\"short\" name=\"lan_domain\">local</textarea>
          <label>Gateway aliases (one per line)</label>
          <textarea class=\"short\" name=\"gateway_aliases\">atomixos</textarea>
          <label>Gateway hostname pattern</label>
          <textarea class=\"short\" name=\"hostname_pattern\">atomixos-{{mac}}</textarea>
          <label>Required activation units (one per line)</label>
          <textarea class=\"short\" name=\"required\"></textarea>
          <label>Container TOML snippet</label>
          <textarea name=\"quadlet\">[container.myapp]
privileged = false

[container.myapp.Unit]
Description = \"My App\"

[container.myapp.Container]
Image = \"ghcr.io/example/myapp:latest\"
PublishPort = [\"10080:8080\"]

[container.myapp.Install]
WantedBy = [\"default.target\"]
</textarea>
          <button type=\"submit\">Generate config.toml</button>
        </form>
      </section>
      {message_block}
    </main>
  </body>
</html>
"""

PROVISIONED_BOOTSTRAP_HTML = BOOTSTRAP_HTML.replace(
    """      <section class=\"grid\">
        <form class=\"panel\" method=\"post\" action=\"/apply\" enctype=\"multipart/form-data\">""",
    """      <section class=\"message\">
        <p><strong>Device already provisioned.</strong> Re-apply requires signed API requests; the browser forms are
        only available during first provisioning.</p>
      </section>
      <section class=\"grid\" style=\"display: none\">
        <form class=\"panel\" method=\"post\" action=\"/apply\" enctype=\"multipart/form-data\">""",
)


class BootstrapHandler(BaseHTTPRequestHandler):
    config_root = None
    output_path = None
    nonce_store = NonceStore()
    apply_lock = threading.Lock()

    def _is_provisioned(self) -> bool:
        """Check if the device already has an active config.

        Recovery of interrupted promotions is intentionally NOT performed here.
        The do_POST path calls recover_config_root() under the apply_lock before
        invoking _do_POST_locked(), so mutating paths always see a consistent
        state.  The GET /api/nonce path only needs a best-effort check.
        """
        return (Path(self.config_root) / "config.toml").exists()

    def _require_auth(self, payload: bytes) -> bool:
        """Verify re-apply authentication. Returns True if authorized."""
        nonce = self.headers.get("X-Atomicnix-Nonce", "")
        signature_b64 = self.headers.get("X-Atomicnix-Signature", "")

        if not nonce or not signature_b64:
            self._send_json(401, {"ok": False, "error": AUTH_REQUIRED_MESSAGE})
            return False

        if not self.nonce_store.consume(nonce):
            self._send_json(401, {"ok": False, "error": "invalid or expired nonce"})
            return False

        try:
            signature_blob = base64.b64decode(signature_b64)
        except Exception:
            self._send_json(401, {"ok": False, "error": "invalid signature encoding"})
            return False

        allowed_signers_path = build_allowed_signers(Path(self.config_root))
        if allowed_signers_path is None:
            self._send_json(401, {"ok": False, "error": "no admin keys available for verification"})
            return False

        try:
            message = reapply_signature_message(nonce, urlparse(self.path).path, payload)
            if not verify_ssh_signature(message, signature_blob, allowed_signers_path):
                self._send_json(401, {"ok": False, "error": "signature verification failed"})
                return False
        finally:
            allowed_signers_path.unlink(missing_ok=True)

        return True

    def _mark_applied(self):
        output_path = getattr(self, "output_path", None)
        if not output_path:
            return
        Path(output_path).write_text("applied\n")

    def _run_post_response_async(self):
        command = os.environ.get(BOOTSTRAP_POST_RESPONSE_ENV)
        if not command:
            return
        subprocess.Popen([command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _activate_services(self) -> list[str]:
        """Run activation services synchronously. Returns list of failed services."""
        command = os.environ.get(BOOTSTRAP_ACTIVATION_ENV) or os.environ.get(BOOTSTRAP_POST_RESPONSE_ENV)
        if not command:
            return []
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

    def _check_required_services(self) -> list[str]:
        """Check that required health services are active. Returns failed units."""
        config_root = Path(self.config_root)
        health_path = config_root / "health-required.json"
        if not health_path.exists():
            return []
        try:
            required = json.loads(health_path.read_text())
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(required, list) or not required:
            return []

        runtime_modes = self._load_runtime_unit_modes()
        failed = []
        for unit in required:
            service = f"{unit}.service"
            mode = runtime_modes.get(service, "rootful")
            try:
                if mode == "rootless":
                    result = self._check_rootless_service(service)
                else:
                    result = subprocess.run(["systemctl", "is-active", "--quiet", service], timeout=10)  # noqa: S607
                if result.returncode != 0:
                    failed.append(service)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                failed.append(service)
        return failed

    def _load_runtime_unit_modes(self) -> dict[str, str]:
        runtime_path = Path(self.config_root) / RUNTIME_METADATA_FILENAME
        try:
            runtime = json.loads(runtime_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
        modes = {}
        for unit in runtime.get("units", []):
            if isinstance(unit, dict) and isinstance(unit.get("service"), str):
                modes[unit["service"]] = unit.get("mode", "rootful")
        return modes

    def _check_rootless_service(self, service: str) -> subprocess.CompletedProcess:
        try:
            uid = pwd.getpwnam(APP_RUNTIME_USER).pw_uid
        except KeyError:
            return subprocess.CompletedProcess([], 1)
        runtime_dir = f"/run/user/{uid}"
        return subprocess.run(
            [  # noqa: S607
                "runuser", "-u", APP_RUNTIME_USER, "--", "env",
                f"HOME=/var/lib/{APP_RUNTIME_USER}",
                f"XDG_RUNTIME_DIR={runtime_dir}",
                f"DBUS_SESSION_BUS_ADDRESS=unix:path={runtime_dir}/bus",
                "systemctl", "--user", "is-active", "--quiet", service,
            ],
            timeout=10,
        )

    def _complete_reapply(self) -> tuple[bool, list[str], bool]:
        activation_failures = self._activate_services()
        health_failures = [] if activation_failures else self._check_required_services()
        failures = activation_failures + health_failures
        if failures:
            config_root = Path(self.config_root)
            restored = restore_rollback(config_root)
            if restored:
                # Re-activate with restored config.
                self._activate_services()
            return False, failures, restored
        cleanup_rollback(Path(self.config_root))
        return True, [], False

    def _write_payload(self, payload: bytes, filename: str = "config.toml"):
        config_root = Path(self.config_root)
        temp_bundle, prepared_config, prepared_files = prepare_source_bytes(payload, filename)
        try:
            recover_config_root(config_root)
            is_reapply = (config_root / "config.toml").exists()
            if is_reapply:
                # Atomic re-apply: candidate → promote → rollback preserved.
                candidate_root = config_root.parent / (config_root.name + CANDIDATE_SUFFIX)
                rollback_root = config_root.parent / (config_root.name + ROLLBACK_SUFFIX)

                if candidate_root.exists():
                    shutil.rmtree(candidate_root)
                candidate_root.mkdir(parents=True, exist_ok=True)

                try:
                    parsed = load_config(prepared_config, config_root)
                    write_imported_state(parsed, prepared_config, prepared_files, candidate_root)
                    carry_forward_managed_state(config_root, candidate_root)
                except Exception:
                    shutil.rmtree(candidate_root, ignore_errors=True)
                    raise

                if rollback_root.exists():
                    shutil.rmtree(rollback_root)
                promotion_marker_path(config_root).write_text("pending\n")
                config_root.rename(rollback_root)
                candidate_root.rename(config_root)
            else:
                # Fresh provisioning: write directly.
                parsed = load_config(prepared_config, config_root)
                write_imported_state(parsed, prepared_config, prepared_files, config_root)

            return prepared_config.read_text()
        finally:
            temp_bundle.cleanup()

    def _read_multipart_form(self, body: bytes):
        content_type = self.headers.get("Content-Type", "")
        message = BytesParser(policy=email.policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
        )
        form = {}
        for part in message.iter_parts():
            name = part.get_param("name", header="Content-Disposition")
            if not name:
                continue
            payload = part.get_payload(decode=True) or b""
            filename = part.get_param("filename", header="Content-Disposition")
            if filename:
                form[name] = {
                    "filename": Path(filename).name,
                    "body": payload,
                }
                continue
            charset = part.get_content_charset("utf-8") or "utf-8"
            form[name] = payload.decode(charset)
        return form

    def _read_body(self) -> bytes:
        """Read request body with size limit enforcement."""
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_REQUEST_BODY_BYTES:
            raise ValueError(f"request body too large ({length} bytes, max {MAX_REQUEST_BODY_BYTES})")
        return self.rfile.read(length)

    def _read_form(self):
        body = self._read_body()
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("multipart/form-data"):
            return self._read_multipart_form(body)
        return {k: v[-1] for k, v in parse_qs(body.decode(), keep_blank_values=True).items()}

    def _send_html(self, config_text="", message=""):
        message_block = f'<section class="message">{message}</section>' if message else ""
        template = PROVISIONED_BOOTSTRAP_HTML if self._is_provisioned() else BOOTSTRAP_HTML
        body = template.format(config_text=html.escape(config_text), message_block=message_block)
        body_bytes = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def _send_json(self, status: int, payload: dict):
        body_bytes = (json.dumps(payload) + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def do_GET(self):
        request = urlparse(self.path)
        if request.path == "/api/nonce":
            if not self._is_provisioned():
                self._send_json(
                    200,
                    {"ok": True, "nonce": "", "message": "device is unprovisioned; no authentication required"},
                )
                return
            nonce = self.nonce_store.issue()
            self._send_json(200, {"ok": True, "nonce": nonce})
            return
        if request.path == "/assets/atomixos.png":
            if not BOOTSTRAP_LOGO_PATH.is_file():
                self.send_error(404)
                return

            body = BOOTSTRAP_LOGO_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._send_html()

    def do_POST(self):
        with self.apply_lock:
            if self.path in ("/api/config", "/apply", "/generate"):
                recover_config_root(Path(self.config_root))
            self._do_POST_locked()

    def _do_POST_locked(self):
        was_provisioned = self._is_provisioned()
        if (
            self.path in ("/api/config", "/apply", "/generate")
            and was_provisioned
            and (not self.headers.get("X-Atomicnix-Nonce") or not self.headers.get("X-Atomicnix-Signature"))
        ):
            self._send_json(401, {"ok": False, "error": AUTH_REQUIRED_MESSAGE})
            return

        if self.path == "/api/config":
            try:
                payload = self._read_body()
            except ValueError as exc:
                self._send_json(413, {"ok": False, "error": str(exc)})
                return
            filename = self.headers.get("X-Config-Filename", "config.toml")
            if was_provisioned and not self._require_auth(payload):
                return
            try:
                self._write_payload(payload, filename)
            except Exception as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
                return

            # Activate services synchronously for re-apply; rollback on failure.
            if was_provisioned:
                ok, failures, restored = self._complete_reapply()
                if not ok:
                    self._send_json(502, {
                        "ok": False,
                        "error": "activation failed; rolled back to previous config",
                        "failures": failures,
                        "rolled_back": restored,
                    })
                    return
            else:
                # First provisioning: fire-and-forget activation.
                self._run_post_response_async()

            self._send_json(200, {"ok": True, "message": "Configuration applied."})
            self._mark_applied()
            return

        form = self._read_form()
        config_text = ""
        try:
            if self.path == "/apply":
                uploaded = form.get("config_file")
                if isinstance(uploaded, dict) and uploaded.get("body"):
                    payload = uploaded["body"]
                    filename = uploaded.get("filename", "config.toml")
                    config_text = uploaded_config_text(payload, filename)
                else:
                    config_text = form.get("config", "")
                    payload = config_text.encode("utf-8")
                    filename = "config.toml"
            elif self.path == "/generate":
                ssh_keys = [line.strip() for line in form.get("ssh_keys", "").splitlines() if line.strip()]
                wan_tcp_ports = [int(line.strip()) for line in form.get("wan_tcp", "").splitlines() if line.strip()]
                wan_udp_ports = [int(line.strip()) for line in form.get("wan_udp", "").splitlines() if line.strip()]
                lan_tcp_ports = [int(line.strip()) for line in form.get("lan_tcp", "").splitlines() if line.strip()]
                lan_udp_ports = [int(line.strip()) for line in form.get("lan_udp", "").splitlines() if line.strip()]
                os_upgrade_server_url = form.get("os_upgrade_server_url", "").strip()
                gateway_cidr = form.get("gateway_cidr", DEFAULT_LAN_GATEWAY_CIDR).strip() or DEFAULT_LAN_GATEWAY_CIDR
                dhcp_start = form.get("dhcp_start", DEFAULT_LAN_DHCP_START).strip() or DEFAULT_LAN_DHCP_START
                dhcp_end = form.get("dhcp_end", DEFAULT_LAN_DHCP_END).strip() or DEFAULT_LAN_DHCP_END
                lan_domain = form.get("lan_domain", DEFAULT_LAN_DOMAIN).strip() or DEFAULT_LAN_DOMAIN
                gateway_aliases = [
                    line.strip() for line in form.get("gateway_aliases", "").splitlines() if line.strip()
                ]
                hostname_pattern = (
                    form.get("hostname_pattern", DEFAULT_LAN_HOSTNAME_PATTERN).strip() or DEFAULT_LAN_HOSTNAME_PATTERN
                )
                quadlet = form.get("quadlet", "").strip()
                required = [line.strip() for line in form.get("required", "").splitlines() if line.strip()]
                if not required:
                    required = generated_required_units(quadlet)
                firewall_lines = []
                if wan_tcp_ports or wan_udp_ports:
                    firewall_lines.extend(["[network.firewall.inbound.wan]"])
                    if wan_tcp_ports:
                        firewall_lines.append(f"tcp = {json.dumps(wan_tcp_ports)}")
                    if wan_udp_ports:
                        firewall_lines.append(f"udp = {json.dumps(wan_udp_ports)}")
                if lan_tcp_ports or lan_udp_ports:
                    if firewall_lines:
                        firewall_lines.append("")
                    firewall_lines.extend(["[network.firewall.inbound.lan]"])
                    if lan_tcp_ports:
                        firewall_lines.append(f"tcp = {json.dumps(lan_tcp_ports)}")
                    if lan_udp_ports:
                        firewall_lines.append(f"udp = {json.dumps(lan_udp_ports)}")
                firewall_text = "\n".join(firewall_lines)
                lan_lines = [
                    "[network.dnsmasq]",
                    f'gateway_cidr = {json.dumps(gateway_cidr)}',
                    f'dhcp_start = {json.dumps(dhcp_start)}',
                    f'dhcp_end = {json.dumps(dhcp_end)}',
                    f'domain = {json.dumps(lan_domain)}',
                    f'gateway_aliases = {json.dumps(gateway_aliases or DEFAULT_LAN_GATEWAY_ALIASES)}',
                ]
                if hostname_pattern:
                    lan_lines.append(f'hostname_pattern = {json.dumps(hostname_pattern)}')
                lan_text = "\n".join(lan_lines)
                ntp_text = "\n".join([
                    "[network.ntp]",
                    f"servers = {json.dumps(DEFAULT_NTP_SERVERS)}",
                ])
                os_upgrade_text = ""
                if os_upgrade_server_url:
                    os_upgrade_text = textwrap.dedent(
                        f"""
                        [os_upgrade]
                        server_url = {json.dumps(os_upgrade_server_url)}
                        """
                    ).strip()
                quadlet = re.sub(r"^\[container\.", "[containers.container.", quadlet, flags=re.MULTILINE)
                quadlet = re.sub(r"^\[network\.", "[containers.network.", quadlet, flags=re.MULTILINE)
                quadlet = re.sub(r"^\[volume\.", "[containers.volume.", quadlet, flags=re.MULTILINE)
                quadlet = re.sub(r"^\[build\.", "[containers.build.", quadlet, flags=re.MULTILINE)
                config_text = textwrap.dedent(
                    f"""
                    version = 2

                    [users.admin]
                    isAdmin = true
                    ssh_key = {json.dumps(ssh_keys[0] if ssh_keys else "")}

                    {generated_extra_users(ssh_keys[1:])}

                    {firewall_text}

                    {lan_text}

                    {ntp_text}

                    {os_upgrade_text}

                    [activation]
                    required = {json.dumps(required)}

                    {quadlet}
                    """
                ).strip() + "\n"
                payload = config_text.encode("utf-8")
                filename = "config.toml"
            else:
                self.send_error(404)
                return

            if was_provisioned and not self._require_auth(payload):
                return
            applied_config = self._write_payload(payload, filename)
            if was_provisioned:
                ok, failures, restored = self._complete_reapply()
                if not ok:
                    detail = html.escape(json.dumps({"failures": failures, "rolled_back": restored}, indent=2))
                    self._send_html(
                        config_text=config_text,
                        message=(
                            "<p><strong>Error:</strong> activation failed; rolled back to previous config.</p>"
                            f"<pre>{detail}</pre>"
                        ),
                    )
                    return
        except Exception as exc:
            self._send_html(config_text=config_text, message=f"<p><strong>Error:</strong> {html.escape(str(exc))}</p>")
            return

        self._send_html(
            config_text=applied_config,
            message=(
                '<p><strong>Configuration applied.</strong> '
                'Use the button below to save the rendered <code>config.toml</code> directly from this page.</p>'
                '<div class="message-actions">'
                '<button type="button" onclick="downloadAppliedConfig()">Download applied config.toml</button>'
                '</div>'
            ),
        )
        self._mark_applied()
        if not was_provisioned:
            self._run_post_response_async()

    def log_message(self, fmt, *args):
        if fmt == '"%s" %s %s' and args:
            request_line = f"{self.command} {urlparse(self.path).path} {self.request_version}"
            args = (request_line, *args[1:])
        sys.stderr.write("[bootstrap] " + (fmt % args) + "\n")


def serve_bootstrap(config_root: Path, output_path: Path | None, host: str, port: int):
    BootstrapHandler.config_root = str(config_root)
    BootstrapHandler.output_path = str(output_path) if output_path else None
    waiting_for_bind = False
    while True:
        try:
            httpd = ThreadingHTTPServer((host, port), BootstrapHandler)
            break
        except OSError as exc:
            if exc.errno == errno.EADDRNOTAVAIL and host == BOOTSTRAP_LAN_HOST:
                if not waiting_for_bind:
                    sys.stderr.write(f"[bootstrap] waiting for bootstrap address {host}\n")
                    waiting_for_bind = True
                time.sleep(1)
                continue
            raise
    httpd.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("config")

    import_parser = sub.add_parser("import")
    import_parser.add_argument("config")
    import_parser.add_argument("config_root")

    recover_parser = sub.add_parser("recover")
    recover_parser.add_argument("config_root")

    sync_parser = sub.add_parser("sync-quadlet")
    sync_parser.add_argument("config_root")
    sync_parser.add_argument("target_root")
    sync_parser.add_argument("rootless_target", nargs="?")

    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("config_root")
    serve_parser.add_argument("output", nargs="?")
    serve_parser.add_argument("--host", default=BOOTSTRAP_LAN_HOST)
    serve_parser.add_argument("--port", type=int, default=8080)

    args = parser.parse_args()

    try:
        if args.command == "validate":
            for warning in validate_config_source(Path(args.config)):
                print(f"warning: {warning}", file=sys.stderr)
        elif args.command == "import":
            for warning in atomic_import_config(Path(args.config), Path(args.config_root)):
                print(f"warning: {warning}", file=sys.stderr)
        elif args.command == "recover":
            recover_config_root(Path(args.config_root))
        elif args.command == "sync-quadlet":
            sync_quadlet_units(
                Path(args.config_root),
                Path(args.target_root),
                Path(args.rootless_target) if args.rootless_target else None,
            )
        elif args.command == "serve":
            serve_bootstrap(
                Path(args.config_root),
                Path(args.output) if args.output else None,
                args.host,
                args.port,
            )
    except ProvisionError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
