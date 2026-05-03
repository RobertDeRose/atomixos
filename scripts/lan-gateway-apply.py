#!/usr/bin/env python3
import contextlib
import json
import os
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
DEFAULT_DNSMASQ_SETTINGS = (
    "bind-dynamic\n"
    "local-service\n"
    "no-resolv\n"
    "port=53\n"
)
REQUIRED_STRING_FIELDS = (
    "gateway_cidr",
    "gateway_ip",
    "subnet_cidr",
    "netmask",
    "dhcp_start",
    "dhcp_end",
    "domain",
)


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
    with contextlib.suppress(OSError):
        subprocess.run(args, check=False)


def host_names(alias: str, domain: str) -> list[str]:
    names = [alias]
    if "." not in alias:
        names.append(f"{alias}.{domain}")
    return list(dict.fromkeys(names))


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
        f"interface={LAN_INTERFACE}\n"
        + DEFAULT_DNSMASQ_SETTINGS
        + f"dhcp-range={dhcp_start},{dhcp_end},{netmask},24h\n"
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
