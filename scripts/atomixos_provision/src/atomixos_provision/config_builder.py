"""Build config TOML from structured inputs."""

import json
import re
import textwrap
import tomllib

from atomixos_provision.config import (
    DEFAULT_LAN_DHCP_END,
    DEFAULT_LAN_DHCP_START,
    DEFAULT_LAN_DOMAIN,
    DEFAULT_LAN_GATEWAY_ALIASES,
    DEFAULT_LAN_GATEWAY_CIDR,
    DEFAULT_LAN_HOSTNAME_PATTERN,
    DEFAULT_NTP_SERVERS,
    provision_error,
    validate_name,
)

__all__ = ["build_config_from_form"]


def parse_port_lines(raw: str, field: str) -> list[int]:
    """Parse newline-separated port numbers from a form field."""
    ports: list[int] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            port = int(line)
        except ValueError:
            msg = f"{field}: {line!r} is not a valid port number"
            raise provision_error(msg) from None
        if not (1 <= port <= 65535):
            msg = f"{field}: port {port} out of range (1-65535)"
            raise provision_error(msg)
        ports.append(port)
    return ports


def generated_required_units(quadlet: str) -> list[str]:
    """Extract container unit names from a TOML snippet for activation.required."""
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
    if container is None:
        containers = parsed.get("containers")
        if isinstance(containers, dict):
            container = containers.get("container")
    if not isinstance(container, dict) or not container:
        message = "container TOML snippet must define at least one [container.<name>] table"
        raise provision_error(message)

    return [validate_name(name) for name in container]


def generated_extra_users(ssh_keys: list[str]) -> str:
    """Generate TOML blocks for additional admin users beyond the first."""
    blocks: list[str] = []
    for index, ssh_key in enumerate(ssh_keys, start=2):
        blocks.append(
            textwrap.dedent(f"""
                [users.admin{index}]
                isAdmin = true
                ssh_key = {json.dumps(ssh_key)}
            """).strip()
        )
    return "\n\n".join(blocks)


def normalize_quadlet_headers(quadlet: str) -> str:
    """Normalize shorthand Quadlet section headers to containers.* prefix."""
    no_prefix = r"(?!containers\.)"
    quadlet = re.sub(
        rf"^\[{no_prefix}container\.",
        "[containers.container.",
        quadlet,
        flags=re.MULTILINE,
    )
    quadlet = re.sub(
        rf"^\[{no_prefix}network\.",
        "[containers.network.",
        quadlet,
        flags=re.MULTILINE,
    )
    quadlet = re.sub(
        rf"^\[{no_prefix}volume\.",
        "[containers.volume.",
        quadlet,
        flags=re.MULTILINE,
    )
    quadlet = re.sub(
        rf"^\[{no_prefix}build\.",
        "[containers.build.",
        quadlet,
        flags=re.MULTILINE,
    )
    return quadlet


def build_config_from_form(form: dict[str, str]) -> str:
    """Build a complete config.toml string from structured form fields.

    Args:
        form: Dict of form field names to string values. Expected fields:
            - ssh_keys: newline-separated SSH public keys
            - wan_tcp, wan_udp, lan_tcp, lan_udp: newline-separated port numbers
            - os_upgrade_server_url: optional OTA server URL
            - gateway_cidr, dhcp_start, dhcp_end, lan_domain: LAN settings
            - gateway_aliases, hostname_pattern: optional LAN settings
            - quadlet: TOML snippet for container definitions
            - required: newline-separated unit names (auto-detected if empty)

    Returns:
        Complete config.toml content as a string.

    Raises:
        ProvisionError: If form fields are invalid.
    """
    ssh_keys = [line.strip() for line in form.get("ssh_keys", "").splitlines() if line.strip()]
    if not ssh_keys:
        raise provision_error("at least one SSH public key is required")

    wan_tcp_ports = parse_port_lines(form.get("wan_tcp", ""), "WAN TCP")
    wan_udp_ports = parse_port_lines(form.get("wan_udp", ""), "WAN UDP")
    lan_tcp_ports = parse_port_lines(form.get("lan_tcp", ""), "LAN TCP")
    lan_udp_ports = parse_port_lines(form.get("lan_udp", ""), "LAN UDP")

    os_upgrade_server_url = form.get("os_upgrade_server_url", "").strip()
    gateway_cidr = (
        form.get("gateway_cidr", DEFAULT_LAN_GATEWAY_CIDR).strip() or DEFAULT_LAN_GATEWAY_CIDR
    )
    dhcp_start = form.get("dhcp_start", DEFAULT_LAN_DHCP_START).strip() or DEFAULT_LAN_DHCP_START
    dhcp_end = form.get("dhcp_end", DEFAULT_LAN_DHCP_END).strip() or DEFAULT_LAN_DHCP_END
    lan_domain = form.get("lan_domain", DEFAULT_LAN_DOMAIN).strip() or DEFAULT_LAN_DOMAIN
    gateway_aliases = [
        line.strip() for line in form.get("gateway_aliases", "").splitlines() if line.strip()
    ]
    hostname_pattern = (
        form.get("hostname_pattern", DEFAULT_LAN_HOSTNAME_PATTERN).strip()
        or DEFAULT_LAN_HOSTNAME_PATTERN
    )
    quadlet = form.get("quadlet", "").strip()
    quadlet = normalize_quadlet_headers(quadlet)
    required = [line.strip() for line in form.get("required", "").splitlines() if line.strip()]
    if not required:
        required = generated_required_units(quadlet)

    # Build firewall section
    firewall_lines: list[str] = []
    if wan_tcp_ports or wan_udp_ports:
        firewall_lines.append("[network.firewall.inbound.wan]")
        if wan_tcp_ports:
            firewall_lines.append(f"tcp = {json.dumps(wan_tcp_ports)}")
        if wan_udp_ports:
            firewall_lines.append(f"udp = {json.dumps(wan_udp_ports)}")
    if lan_tcp_ports or lan_udp_ports:
        if firewall_lines:
            firewall_lines.append("")
        firewall_lines.append("[network.firewall.inbound.lan]")
        if lan_tcp_ports:
            firewall_lines.append(f"tcp = {json.dumps(lan_tcp_ports)}")
        if lan_udp_ports:
            firewall_lines.append(f"udp = {json.dumps(lan_udp_ports)}")
    firewall_text = "\n".join(firewall_lines)

    # Build LAN section
    lan_lines = [
        "[network.dnsmasq]",
        f"gateway_cidr = {json.dumps(gateway_cidr)}",
        f"dhcp_start = {json.dumps(dhcp_start)}",
        f"dhcp_end = {json.dumps(dhcp_end)}",
        f"domain = {json.dumps(lan_domain)}",
        f"gateway_aliases = {json.dumps(gateway_aliases or list(DEFAULT_LAN_GATEWAY_ALIASES))}",
    ]
    if hostname_pattern:
        lan_lines.append(f"hostname_pattern = {json.dumps(hostname_pattern)}")
    lan_text = "\n".join(lan_lines)

    # Build NTP section
    ntp_text = "\n".join(
        [
            "[network.ntp]",
            f"servers = {json.dumps(DEFAULT_NTP_SERVERS)}",
        ]
    )

    # Build OS upgrade section
    os_upgrade_text = ""
    if os_upgrade_server_url:
        os_upgrade_text = textwrap.dedent(f"""
            [os_upgrade]
            server_url = {json.dumps(os_upgrade_server_url)}
        """).strip()

    # Assemble final config
    sections = [
        "\n".join(
            [
                "version = 1",
                "",
                "[users.admin]",
                "isAdmin = true",
                f"ssh_key = {json.dumps(ssh_keys[0] if ssh_keys else '')}",
            ]
        ),
        generated_extra_users(ssh_keys[1:]),
        firewall_text,
        lan_text,
        ntp_text,
        os_upgrade_text,
        "\n".join(
            [
                "[activation]",
                f"required = {json.dumps(required)}",
            ]
        ),
        quadlet,
    ]
    config_text = "\n\n".join(section for section in sections if section).strip() + "\n"

    return config_text
