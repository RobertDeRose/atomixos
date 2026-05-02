#!/usr/bin/env python3
import json
import os
import re
import subprocess
from pathlib import Path


CONFIG_FILE = Path(os.environ.get("ATOMIXOS_FIREWALL_INBOUND_FILE", "/data/config/firewall-inbound.json"))
RULE_COMMENT = os.environ.get("ATOMIXOS_FIREWALL_RULE_COMMENT", "ATOMIXOS_PROVISIONED_INBOUND")
WAN_INTERFACE = os.environ.get("ATOMIXOS_FIREWALL_WAN_INTERFACE", "eth0")
NFT = os.environ.get("ATOMIXOS_NFT", "nft")
INTERFACE_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")


def validate_ports(value: object, path: str) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list):
        msg = f"expected array at {path}"
        raise ValueError(msg)

    ports: list[int] = []
    for idx, item in enumerate(value):
        if not isinstance(item, int) or isinstance(item, bool) or not 1 <= item <= 65535:
            msg = f"expected port integer in range 1..65535 at {path}[{idx}]"
            raise ValueError(msg)
        ports.append(item)
    return ports


def validate_interface_name(name: str) -> str:
    if not INTERFACE_PATTERN.fullmatch(name):
        msg = f"invalid interface name: {name!r}"
        raise ValueError(msg)
    return name


def main() -> int:
    if not CONFIG_FILE.exists():
        return 0

    payload = json.loads(CONFIG_FILE.read_text())
    wan_interface = validate_interface_name(WAN_INTERFACE)
    existing = subprocess.run(
        [NFT, "-a", "list", "chain", "inet", "filter", "input"],
        capture_output=True,
        check=False,
        text=True,
    )

    commands: list[str] = []
    for line in existing.stdout.splitlines():
        if RULE_COMMENT not in line:
            continue
        match = re.search(r"handle (\d+)$", line)
        if match:
            commands.append(f"delete rule inet filter input handle {match.group(1)}")

    for proto in ("tcp", "udp"):
        ports = validate_ports(payload.get(proto), f"firewall-inbound.{proto}")
        if not ports:
            continue
        joined = ", ".join(str(port) for port in ports)
        commands.append(
            f'add rule inet filter input iifname "{wan_interface}" {proto} dport {{ {joined} }} '
            f'accept comment "{RULE_COMMENT}"'
        )

    if commands:
        subprocess.run([NFT, "-f", "-"], input="\n".join(commands), text=True, check=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
