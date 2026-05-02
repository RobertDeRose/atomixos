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


def main() -> int:
    if not CONFIG_FILE.exists():
        return 0

    payload = json.loads(CONFIG_FILE.read_text())
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
        ports = payload.get(proto, [])
        if not ports:
            continue
        joined = ", ".join(str(port) for port in ports)
        commands.append(
            f'add rule inet filter input iifname "{WAN_INTERFACE}" {proto} dport {{ {joined} }} '
            f'accept comment "{RULE_COMMENT}"'
        )

    if commands:
        subprocess.run([NFT, "-f", "-"], input="\n".join(commands), text=True, check=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
