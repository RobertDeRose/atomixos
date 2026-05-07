#!/usr/bin/env python3
import ipaddress
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


CONFIG_FILE = Path(os.environ.get("ATOMIXOS_LAN_SETTINGS_FILE", "/data/config/lan-settings.json"))
DNSMASQ_CONFIG_DIR = Path(os.environ.get("ATOMIXOS_DNSMASQ_CONFIG_DIR", "/etc/dnsmasq.d"))
DNSMASQ_CONFIG_FILE = DNSMASQ_CONFIG_DIR / "atomixos-lan.conf"
DNSMASQ_HOSTS_FILE = Path(os.environ.get("ATOMIXOS_DNSMASQ_HOSTS_FILE", "/etc/atomixos/dnsmasq-hosts"))
CHRONY_LAN_FILE = Path(os.environ.get("ATOMIXOS_CHRONY_LAN_FILE", "/etc/atomixos/chrony-lan.conf"))
NETWORK_FILE = Path(
    os.environ.get(
        "ATOMIXOS_LAN_NETWORK_FILE",
        "/etc/systemd/network/20-lan.network.d/50-atomixos.conf",
    )
)
ETC_HOSTS_FILE = Path(os.environ.get("ATOMIXOS_ETC_HOSTS_FILE", "/etc/hosts"))
LAN_INTERFACE = os.environ.get("ATOMIXOS_LAN_INTERFACE", "eth1")
SYS_CLASS_NET_DIR = Path(os.environ.get("ATOMIXOS_SYS_CLASS_NET_DIR", "/sys/class/net"))
REQUIRED_STRING_FIELDS = (
    "gateway_cidr",
    "gateway_ip",
    "subnet_cidr",
    "netmask",
    "dhcp_start",
    "dhcp_end",
    "domain",
)
DNS_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def replace_file(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == content:
        return False

    with tempfile.NamedTemporaryFile(
        "w",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)

    temp_path.chmod(0o644)
    temp_path.replace(path)
    return True


def read_mac_suffix(interface: str) -> str:
    address_path = SYS_CLASS_NET_DIR / interface / "address"
    try:
        raw = address_path.read_text().strip().lower()
    except OSError:
        return ""

    octets = raw.split(":")
    if len(octets) != 6 or any(len(octet) != 2 for octet in octets):
        return ""
    if any(any(char not in "0123456789abcdef" for char in octet) for octet in octets):
        return ""
    return "".join(octets)


def run_command(args: list[str]) -> None:
    try:
        subprocess.run(args, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        msg = f"command failed: {' '.join(args)}: {exc}"
        raise ValueError(msg) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = stderr or stdout or f"exit status {exc.returncode}"
        msg = f"command failed: {' '.join(args)}: {detail}"
        raise ValueError(msg) from exc


def host_names(alias: str, domain: str) -> list[str]:
    names = [alias]
    if "." not in alias:
        names.append(f"{alias}.{domain}")
    return list(dict.fromkeys(names))


def parse_ipv4_interface(value: str, key: str) -> ipaddress.IPv4Interface:
    try:
        return ipaddress.IPv4Interface(value)
    except ipaddress.AddressValueError as exc:
        msg = f"{key} must be a valid IPv4 interface in {CONFIG_FILE}: {value!r}"
        raise ValueError(msg) from exc
    except ipaddress.NetmaskValueError as exc:
        msg = f"{key} must be a valid IPv4 interface in {CONFIG_FILE}: {value!r}"
        raise ValueError(msg) from exc


def parse_ipv4_address(value: str, key: str) -> ipaddress.IPv4Address:
    try:
        return ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        msg = f"{key} must be a valid IPv4 address in {CONFIG_FILE}: {value!r}"
        raise ValueError(msg) from exc


def parse_ipv4_network(value: str, key: str) -> ipaddress.IPv4Network:
    try:
        return ipaddress.IPv4Network(value, strict=True)
    except ipaddress.AddressValueError as exc:
        msg = f"{key} must be a valid IPv4 network in {CONFIG_FILE}: {value!r}"
        raise ValueError(msg) from exc
    except ipaddress.NetmaskValueError as exc:
        msg = f"{key} must be a valid IPv4 network in {CONFIG_FILE}: {value!r}"
        raise ValueError(msg) from exc
    except ValueError as exc:
        msg = f"{key} must be a valid IPv4 network in {CONFIG_FILE}: {value!r}"
        raise ValueError(msg) from exc


def validate_dns_name(value: str, key: str) -> str:
    if len(value) > 253:
        msg = f"{key} must be a valid DNS name in {CONFIG_FILE}: {value!r}"
        raise ValueError(msg)

    labels = value.split(".")
    if not labels or any(not label or not DNS_LABEL_PATTERN.fullmatch(label) for label in labels):
        msg = f"{key} must be a valid DNS name in {CONFIG_FILE}: {value!r}"
        raise ValueError(msg)
    return value


def require_string(payload: dict[str, object], key: str) -> str:
    if key not in payload:
        msg = f"missing required key '{key}' in {CONFIG_FILE}"
        raise ValueError(msg)

    value = payload[key]
    if not isinstance(value, str) or not value:
        msg = f"{key} must be a non-empty string in {CONFIG_FILE}"
        raise ValueError(msg)
    return value


def optional_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key, "")
    if not isinstance(value, str):
        msg = f"{key} must be a string in {CONFIG_FILE}"
        raise ValueError(msg)
    return value


def gateway_aliases(payload: dict[str, object]) -> list[str]:
    aliases = payload.get("gateway_aliases", [])
    if not isinstance(aliases, list) or any(not isinstance(alias, str) or not alias for alias in aliases):
        msg = f"gateway_aliases must be a list of non-empty strings in {CONFIG_FILE}"
        raise ValueError(msg)
    return aliases


def load_settings() -> dict[str, object]:
    try:
        raw_payload = json.loads(CONFIG_FILE.read_text())
    except OSError as exc:
        msg = f"unable to read {CONFIG_FILE}: {exc}"
        raise ValueError(msg) from exc
    except json.JSONDecodeError as exc:
        msg = f"invalid JSON in {CONFIG_FILE}: {exc.msg}"
        raise ValueError(msg) from exc

    if not isinstance(raw_payload, dict):
        msg = f"{CONFIG_FILE} must contain a JSON object"
        raise ValueError(msg)

    payload = dict(raw_payload)
    for key in REQUIRED_STRING_FIELDS:
        payload[key] = require_string(payload, key)
    payload["hostname_pattern"] = optional_string(payload, "hostname_pattern")
    payload["gateway_aliases"] = gateway_aliases(payload)

    gateway = parse_ipv4_interface(payload["gateway_cidr"], "gateway_cidr")
    gateway_ip = parse_ipv4_address(payload["gateway_ip"], "gateway_ip")
    subnet = parse_ipv4_network(payload["subnet_cidr"], "subnet_cidr")
    dhcp_start = parse_ipv4_address(payload["dhcp_start"], "dhcp_start")
    dhcp_end = parse_ipv4_address(payload["dhcp_end"], "dhcp_end")
    parse_ipv4_network(f"0.0.0.0/{payload['netmask']}", "netmask")
    domain = validate_dns_name(payload["domain"], "domain")

    hostname_pattern = payload["hostname_pattern"]
    if hostname_pattern:
        if "{mac}" not in hostname_pattern:
            msg = f"hostname_pattern must include '{{mac}}' in {CONFIG_FILE}"
            raise ValueError(msg)
        validate_dns_name(hostname_pattern.replace("{mac}", "001122334455"), "hostname_pattern")

    aliases = [validate_dns_name(alias, "gateway_aliases") for alias in payload["gateway_aliases"]]

    if gateway.ip != gateway_ip:
        msg = f"gateway_ip must match gateway_cidr in {CONFIG_FILE}"
        raise ValueError(msg)
    if gateway.network != subnet:
        msg = f"subnet_cidr must match gateway_cidr in {CONFIG_FILE}"
        raise ValueError(msg)
    if str(gateway.netmask) != payload["netmask"]:
        msg = f"netmask must match gateway_cidr in {CONFIG_FILE}"
        raise ValueError(msg)
    if dhcp_start not in subnet or dhcp_end not in subnet:
        msg = f"dhcp_start and dhcp_end must be inside subnet_cidr in {CONFIG_FILE}"
        raise ValueError(msg)
    if int(dhcp_start) > int(dhcp_end):
        msg = f"dhcp_start must be less than or equal to dhcp_end in {CONFIG_FILE}"
        raise ValueError(msg)
    if int(dhcp_start) <= int(gateway_ip) <= int(dhcp_end):
        msg = f"dhcp_start and dhcp_end must not include gateway_ip in {CONFIG_FILE}"
        raise ValueError(msg)

    payload["gateway_cidr"] = str(gateway)
    payload["gateway_ip"] = str(gateway_ip)
    payload["subnet_cidr"] = str(subnet)
    payload["netmask"] = str(gateway.netmask)
    payload["dhcp_start"] = str(dhcp_start)
    payload["dhcp_end"] = str(dhcp_end)
    payload["domain"] = domain
    payload["gateway_aliases"] = aliases
    return payload


def main() -> int:
    if not CONFIG_FILE.exists():
        return 0

    payload = load_settings()

    gateway_cidr = payload["gateway_cidr"]
    gateway_ip = payload["gateway_ip"]
    subnet_cidr = payload["subnet_cidr"]
    netmask = payload["netmask"]
    dhcp_start = payload["dhcp_start"]
    dhcp_end = payload["dhcp_end"]
    domain = payload["domain"]
    aliases = payload.get("gateway_aliases", [])
    hostname_pattern = payload.get("hostname_pattern", "")

    gateway_names: list[str] = []
    if hostname_pattern:
        mac_suffix = read_mac_suffix(LAN_INTERFACE)
        if mac_suffix:
            gateway_names.append(hostname_pattern.replace("{mac}", mac_suffix))
    gateway_names.extend(aliases)

    resolved_names: list[str] = []
    for name in gateway_names:
        if name and name not in resolved_names:
            resolved_names.append(name)

    network_changed = replace_file(
        NETWORK_FILE,
        "[Network]\n" f"Address={gateway_cidr}\n",
    )

    dnsmasq_changed = replace_file(
        DNSMASQ_CONFIG_FILE,
        f"dhcp-range={dhcp_start},{dhcp_end},{netmask},24h\n"
        + f"dhcp-option=3,{gateway_ip}\n"
        + f"dhcp-option=6,{gateway_ip}\n"
        + f"dhcp-option=42,{gateway_ip}\n"
        + f"domain={domain}\n"
        + "expand-hosts\n"
        + f"addn-hosts={DNSMASQ_HOSTS_FILE}\n"
        + f"local=/{domain}/\n"
        + "log-dhcp\n"
    )

    dnsmasq_hosts_changed = replace_file(
        DNSMASQ_HOSTS_FILE,
        "\n".join(f"{gateway_ip} {' '.join(host_names(alias, domain))}" for alias in resolved_names)
        + ("\n" if resolved_names else ""),
    )

    chrony_changed = replace_file(
        CHRONY_LAN_FILE,
        "# Managed by lan-gateway-apply\n" f"allow {subnet_cidr}\n",
    )

    existing_hosts: list[str] = []
    if ETC_HOSTS_FILE.exists():
        existing_hosts = [
            line for line in ETC_HOSTS_FILE.read_text().splitlines() if "# ATOMIXOS_LAN_GATEWAY" not in line
        ]
        while existing_hosts and existing_hosts[-1] == "":
            existing_hosts.pop()

    for alias in resolved_names:
        existing_hosts.append(
            f"{gateway_ip} {' '.join(host_names(alias, domain))} # ATOMIXOS_LAN_GATEWAY"
        )
    replace_file(ETC_HOSTS_FILE, "\n".join(existing_hosts) + "\n")

    if network_changed:
        run_command(["networkctl", "reload"])
        run_command(["systemctl", "try-restart", "systemd-networkd.service"])

    if dnsmasq_changed or dnsmasq_hosts_changed:
        run_command(["systemctl", "try-restart", "dnsmasq.service"])

    if chrony_changed:
        run_command(["systemctl", "try-restart", "chronyd.service"])

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"[lan-gateway-apply] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
