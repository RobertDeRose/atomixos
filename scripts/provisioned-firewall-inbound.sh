#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE="/data/config/firewall-inbound.json"
RULE_COMMENT="ATOMIXOS_PROVISIONED_INBOUND"

if [ ! -f "$CONFIG_FILE" ]; then
	exit 0
fi

commands="$(
	python3 - "$CONFIG_FILE" "$RULE_COMMENT" <<'PY'
import json
import re
import subprocess
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
comment = sys.argv[2]
payload = json.loads(config_path.read_text())

existing = subprocess.run(
    ["nft", "-a", "list", "chain", "inet", "filter", "input"],
    capture_output=True,
    check=False,
    text=True,
)

commands = []
for line in existing.stdout.splitlines():
    if comment not in line:
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
        f'add rule inet filter input iifname "eth0" {proto} dport {{ {joined} }} accept comment "{comment}"'
    )

print("\n".join(commands))
PY
)"

if [ -n "$commands" ]; then
	nft -f - <<<"$commands"
fi
