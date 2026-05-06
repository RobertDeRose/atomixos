#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
from pathlib import Path


CONFIG_FILE = Path(os.environ.get("ATOMIXOS_FIREWALL_INBOUND_FILE", "/data/config/firewall-inbound.json"))
RULE_COMMENT = os.environ.get("ATOMIXOS_FIREWALL_RULE_COMMENT", "ATOMIXOS_PROVISIONED_INBOUND")
WAN_INTERFACE = os.environ.get("ATOMIXOS_FIREWALL_WAN_INTERFACE", "eth0")
NFT = os.environ.get("ATOMIXOS_NFT", "nft")
INTERFACE_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")
RULE_COMMENT_PATTERN = re.compile(r"^[ -~]+$")


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


def validate_rule_comment(comment: str) -> str:
    if not comment:
        msg = "invalid rule comment: empty"
        raise ValueError(msg)
    if len(comment) > 128 or '"' in comment or not RULE_COMMENT_PATTERN.fullmatch(comment):
        msg = f"invalid rule comment: {comment!r}"
        raise ValueError(msg)
    return comment


def load_payload() -> dict[str, object]:
    try:
        payload = json.loads(CONFIG_FILE.read_text())
    except OSError as exc:
        msg = f"unable to read {CONFIG_FILE}: {exc}"
        raise ValueError(msg) from exc
    except json.JSONDecodeError as exc:
        msg = f"invalid JSON in {CONFIG_FILE}: {exc.msg}"
        raise ValueError(msg) from exc

    if not isinstance(payload, dict):
        msg = f"{CONFIG_FILE} must contain a JSON object"
        raise ValueError(msg)
    return dict(payload)


def run_nft(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [NFT, *args],
            capture_output=True,
            check=True,
            input=input_text,
            text=True,
        )
    except FileNotFoundError as exc:
        msg = f"unable to execute nft command {NFT!r}: {exc}"
        raise ValueError(msg) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or f"exit status {exc.returncode}").strip()
        msg = f"nft command failed: {detail}"
        raise ValueError(msg) from exc


def main() -> int:
    rule_comment = validate_rule_comment(RULE_COMMENT)
    wan_interface = validate_interface_name(WAN_INTERFACE)

    if not CONFIG_FILE.exists():
        return 0

    payload = load_payload()
    existing = run_nft("-a", "list", "chain", "inet", "filter", "input")

    commands: list[str] = []
    for line in existing.stdout.splitlines():
        if rule_comment not in line:
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
            f'accept comment "{rule_comment}"'
        )

    if commands:
        run_nft("-f", "-", input_text="\n".join(commands))

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"[provisioned-firewall-inbound] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
