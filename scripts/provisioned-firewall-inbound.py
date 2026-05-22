#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
from pathlib import Path


CONFIG_FILE = Path(os.environ.get("ATOMIXOS_FIREWALL_INBOUND_FILE", "/data/config/firewall-inbound.json"))
RULE_COMMENT = os.environ.get("ATOMIXOS_FIREWALL_RULE_COMMENT", "ATOMIXOS_PROVISIONED_INBOUND")
LAN_DEFAULT_OPEN_COMMENT = "ATOMIXOS_LAN_DEFAULT_OPEN"
WAN_INTERFACE = os.environ.get("ATOMIXOS_FIREWALL_WAN_INTERFACE", "eth0")
LAN_INTERFACE = os.environ.get("ATOMIXOS_FIREWALL_LAN_INTERFACE", "eth1")
NFT = os.environ.get("ATOMIXOS_NFT", "nft")
LAN_REQUIRED_TCP = {22, 53, 8080}
LAN_REQUIRED_UDP = {53, 67, 68, 123}
INTERFACE_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")
RULE_COMMENT_PATTERN = re.compile(r"^[ -~]+$")
NFT_COMMENT_PATTERN = re.compile(r'\bcomment\s+"((?:\\.|[^"\\])*)"')


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


def nft_rule_comment(line: str) -> str | None:
    match = NFT_COMMENT_PATTERN.search(line)
    if not match:
        return None
    try:
        return json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return None


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
    lan_interface = validate_interface_name(LAN_INTERFACE)
    lan_default_open_comment = validate_rule_comment(LAN_DEFAULT_OPEN_COMMENT)
    existing = run_nft("-a", "list", "chain", "inet", "filter", "input")

    commands: list[str] = []
    for line in existing.stdout.splitlines():
        comment = nft_rule_comment(line)
        if comment not in {rule_comment, lan_default_open_comment}:
            continue
        match = re.search(r"handle (\d+)$", line)
        if match:
            commands.append(f"delete rule inet filter input handle {match.group(1)}")

    if not CONFIG_FILE.exists():
        if commands:
            run_nft("-f", "-", input_text="\n".join(commands))
        return 0

    payload = load_payload()

    if not isinstance(payload, dict):
        msg = f"{CONFIG_FILE} must be a JSON object"
        raise ValueError(msg)

    lan_payload = payload.get("lan")
    restrictive_lan = isinstance(lan_payload, dict) and any(
        validate_ports(lan_payload.get(proto), f"firewall-inbound.lan.{proto}")
        for proto in ("tcp", "udp")
    )

    for scope_name, interface in (("wan", wan_interface), ("lan", lan_interface)):
        scope_payload = payload.get(scope_name)
        if scope_payload is None:
            continue
        if not isinstance(scope_payload, dict):
            msg = f"{CONFIG_FILE} {scope_name!r} entry must contain a JSON object"
            raise ValueError(msg)
        for proto in ("tcp", "udp"):
            ports = validate_ports(scope_payload.get(proto), f"firewall-inbound.{scope_name}.{proto}")
            if scope_name == "lan" and restrictive_lan:
                required_ports = LAN_REQUIRED_TCP if proto == "tcp" else LAN_REQUIRED_UDP
                ports = sorted(set(ports) | required_ports)
            if not ports:
                continue
            joined = ", ".join(str(port) for port in ports)
            commands.append(
                f'add rule inet filter input iifname "{interface}" {proto} dport {{ {joined} }} '
                f'accept comment "{rule_comment}"'
            )

    if not restrictive_lan:
        commands.append(
            f'add rule inet filter input iifname "{lan_interface}" accept comment "{lan_default_open_comment}"'
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
