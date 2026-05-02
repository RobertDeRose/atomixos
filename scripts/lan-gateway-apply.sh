#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE="${ATOMIXOS_LAN_SETTINGS_FILE:-/data/config/lan-settings.json}"
DNSMASQ_CONFIG_DIR="${ATOMIXOS_DNSMASQ_CONFIG_DIR:-/etc/dnsmasq.d}"
DNSMASQ_CONFIG_FILE="$DNSMASQ_CONFIG_DIR/atomixos-lan.conf"
DNSMASQ_HOSTS_FILE="${ATOMIXOS_DNSMASQ_HOSTS_FILE:-/etc/atomixos/dnsmasq-hosts}"
CHRONY_LAN_FILE="${ATOMIXOS_CHRONY_LAN_FILE:-/etc/atomixos/chrony-lan.conf}"
NETWORK_FILE="${ATOMIXOS_LAN_NETWORK_FILE:-/etc/systemd/network/20-lan.network.d/50-atomixos.conf}"
ETC_HOSTS_FILE="${ATOMIXOS_ETC_HOSTS_FILE:-/etc/hosts}"
LAN_INTERFACE="${ATOMIXOS_LAN_INTERFACE:-eth1}"
SYS_CLASS_NET_DIR="${ATOMIXOS_SYS_CLASS_NET_DIR:-/sys/class/net}"

if [ ! -f "$CONFIG_FILE" ]; then
	exit 0
fi

python3 - "$CONFIG_FILE" "$DNSMASQ_CONFIG_FILE" "$DNSMASQ_HOSTS_FILE" "$CHRONY_LAN_FILE" "$NETWORK_FILE" "$ETC_HOSTS_FILE" "$LAN_INTERFACE" "$SYS_CLASS_NET_DIR" <<'PY'
import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
dnsmasq_config_path = Path(sys.argv[2])
dnsmasq_hosts_path = Path(sys.argv[3])
chrony_lan_path = Path(sys.argv[4])
network_path = Path(sys.argv[5])
etc_hosts_path = Path(sys.argv[6])
lan_interface = sys.argv[7]
sys_class_net_dir = Path(sys.argv[8])

payload = json.loads(config_path.read_text())

gateway_cidr = payload["gateway_cidr"]
gateway_ip = payload["gateway_ip"]
subnet_cidr = payload["subnet_cidr"]
netmask = payload["netmask"]
dhcp_start = payload["dhcp_start"]
dhcp_end = payload["dhcp_end"]
domain = payload["domain"]
aliases = payload.get("gateway_aliases", [])
hostname_pattern = payload.get("hostname_pattern", "")


def replace_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".{path.name}.tmp"
    temp_path.write_text(content)
    temp_path.chmod(0o644)
    temp_path.replace(path)


def read_mac_suffix(interface: str):
    address_path = sys_class_net_dir / interface / "address"
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


gateway_names = []
if hostname_pattern:
    mac_suffix = read_mac_suffix(lan_interface)
    if mac_suffix:
        gateway_names.append(hostname_pattern.replace("{mac}", mac_suffix))
gateway_names.extend(aliases)

resolved_names = []
for name in gateway_names:
    if not name or name in resolved_names:
        continue
    resolved_names.append(name)

replace_file(
    network_path,
    "[Network]\n"
    f"Address={gateway_cidr}\n"
)

replace_file(
    dnsmasq_config_path,
    f"interface={lan_interface}\n"
    "bind-dynamic\n"
    f"dhcp-range={dhcp_start},{dhcp_end},{netmask},24h\n"
    f"dhcp-option=3,{gateway_ip}\n"
    f"dhcp-option=6,{gateway_ip}\n"
    f"dhcp-option=42,{gateway_ip}\n"
    f"domain={domain}\n"
    "expand-hosts\n"
    f"addn-hosts={dnsmasq_hosts_path}\n"
    "log-dhcp\n"
    "port=53\n"
)

host_lines = []
for alias in resolved_names:
    names = [alias]
    if "." not in alias:
        names.append(f"{alias}.{domain}")
    host_lines.append(f"{gateway_ip} {' '.join(dict.fromkeys(names))}")
replace_file(dnsmasq_hosts_path, "\n".join(host_lines) + ("\n" if host_lines else ""))

replace_file(
    chrony_lan_path,
    "# Managed by lan-gateway-apply\n"
    f"allow {subnet_cidr}\n"
)

existing_hosts = []
if etc_hosts_path.exists():
    existing_hosts = [
        line for line in etc_hosts_path.read_text().splitlines() if "# ATOMIXOS_LAN_GATEWAY" not in line
    ]
    while existing_hosts and existing_hosts[-1] == "":
        existing_hosts.pop()
for alias in resolved_names:
    names = [alias]
    if "." not in alias:
        names.append(f"{alias}.{domain}")
    existing_hosts.append(f"{gateway_ip} {' '.join(dict.fromkeys(names))} # ATOMIXOS_LAN_GATEWAY")
replace_file(etc_hosts_path, "\n".join(existing_hosts) + "\n")
PY

networkctl reload || true
systemctl try-restart systemd-networkd.service || true
systemctl try-restart dnsmasq.service || true
systemctl try-restart chronyd.service || true
