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
HOST_NETWORK_FILE = Path(
    os.environ.get("ATOMIXOS_HOST_NETWORK_FILE", "/data/config/host-network.json")
)
DNSMASQ_CONFIG_DIR = Path(os.environ.get("ATOMIXOS_DNSMASQ_CONFIG_DIR", "/etc/dnsmasq.d"))
DNSMASQ_CONFIG_FILE = DNSMASQ_CONFIG_DIR / "atomixos-lan.conf"
DNSMASQ_HOSTS_FILE = Path(os.environ.get("ATOMIXOS_DNSMASQ_HOSTS_FILE", "/etc/atomixos/dnsmasq-hosts"))
CHRONY_LAN_FILE = Path(os.environ.get("ATOMIXOS_CHRONY_LAN_FILE", "/etc/atomixos/chrony-lan.conf"))
BOOTSTRAP_SOCKET_OVERRIDE = Path(
    os.environ.get(
        "ATOMIXOS_BOOTSTRAP_SOCKET_OVERRIDE",
        "/run/systemd/system/atomixos-bootstrap.socket.d/50-lan-bind.conf",
    )
)
NETWORK_FILE = Path(
    os.environ.get(
        "ATOMIXOS_LAN_NETWORK_FILE",
        "/etc/systemd/network/20-lan.network.d/50-atomixos.conf",
    )
)
HOST_NETWORK_CONFIG_DIR = Path(os.environ.get("ATOMIXOS_HOST_NETWORK_CONFIG_DIR", "/etc/systemd/network"))
ETH0_NETWORK_DROPIN = Path(
    os.environ.get(
        "ATOMIXOS_ETH0_NETWORK_DROPIN",
        "/etc/systemd/network/10-wan.network.d/50-atomixos.conf",
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
DEFAULT_NTP_SERVERS = ["time.cloudflare.com"]
HOST_INTERFACE_RE = re.compile(r"^eth[0-9]+$")


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


def write_bootstrap_socket_rebind(gateway_ip: str) -> None:
    replace_file(
        BOOTSTRAP_SOCKET_OVERRIDE,
        "[Socket]\n"
        "ListenStream=\n"
        f"ListenStream={gateway_ip}:8080\n",
    )


def apply_bootstrap_socket_rebind(gateway_ip: str) -> None:
    write_bootstrap_socket_rebind(gateway_ip)
    run_command(["systemctl", "daemon-reload"])


def host_names(alias: str, domain: str) -> list[str]:
    names = [alias]
    if "." not in alias:
        names.append(f"{alias}.{domain}")
    return list(dict.fromkeys(names))


def parse_ipv4_interface(value: str, key: str) -> ipaddress.IPv4Interface:
    try:
        return ipaddress.IPv4Interface(value)
    except (ipaddress.AddressValueError, ipaddress.NetmaskValueError) as exc:
        msg = f"{key} must be a valid IPv4 interface in {CONFIG_FILE}: {value!r}"
        raise ValueError(msg) from exc


def parse_host_ipv4_interface(value: str, key: str) -> ipaddress.IPv4Interface:
    try:
        return ipaddress.IPv4Interface(value)
    except (ipaddress.AddressValueError, ipaddress.NetmaskValueError) as exc:
        msg = f"{key} must be a valid IPv4 interface in {HOST_NETWORK_FILE}: {value!r}"
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


def ntp_servers(payload: dict[str, object]) -> list[str]:
    servers = payload.get("ntp_servers", DEFAULT_NTP_SERVERS)
    if not isinstance(servers, list) or any(not isinstance(server, str) or not server for server in servers):
        msg = f"ntp_servers must be a list of non-empty strings in {CONFIG_FILE}"
        raise ValueError(msg)
    for server in servers:
        if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in server):
            msg = f"ntp_servers must not contain whitespace or control characters in {CONFIG_FILE}"
            raise ValueError(msg)
        try:
            ipaddress.ip_address(server)
        except ValueError:
            validate_dns_name(server, "ntp_servers")
    return servers


def parse_ip_address(value: str, key: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        return ipaddress.ip_address(value)
    except ValueError as exc:
        msg = f"{key} must be a valid IP address in {HOST_NETWORK_FILE}: {value!r}"
        raise ValueError(msg) from exc


def parse_host_ipv4_address(value: str, key: str) -> ipaddress.IPv4Address:
    try:
        return ipaddress.IPv4Address(value)
    except ValueError as exc:
        msg = f"{key} must be a valid IPv4 address in {HOST_NETWORK_FILE}: {value!r}"
        raise ValueError(msg) from exc


def require_host_keys(payload: dict[str, object], allowed: set[str], path: str) -> None:
    unexpected = set(payload) - allowed
    if unexpected:
        keys = ", ".join(sorted(unexpected))
        msg = f"unsupported keys at {path} in {HOST_NETWORK_FILE}: {keys}"
        raise ValueError(msg)


def require_host_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        msg = f"{key} must be a non-empty string in {HOST_NETWORK_FILE}"
        raise ValueError(msg)
    return value


def host_string_list(payload: dict[str, object], key: str) -> list[str]:
    values = payload.get(key, [])
    if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
        msg = f"{key} must be a list of non-empty strings in {HOST_NETWORK_FILE}"
        raise ValueError(msg)
    return values


def host_ip_list(payload: dict[str, object], key: str) -> list[str]:
    return [str(parse_ip_address(value, key)) for value in host_string_list(payload, key)]


def host_search_domains(payload: dict[str, object], key: str) -> list[str]:
    return [validate_host_dns_name(value, key) for value in host_string_list(payload, key)]


def validate_host_dns_name(value: str, key: str) -> str:
    if len(value) > 253:
        msg = f"{key} must be a valid DNS name in {HOST_NETWORK_FILE}: {value!r}"
        raise ValueError(msg)

    labels = value.split(".")
    if not labels or any(not label or not DNS_LABEL_PATTERN.fullmatch(label) for label in labels):
        msg = f"{key} must be a valid DNS name in {HOST_NETWORK_FILE}: {value!r}"
        raise ValueError(msg)
    return value


def load_host_network_settings() -> dict[str, object]:
    if not HOST_NETWORK_FILE.exists():
        return {"dns_servers": [], "dns_search_domains": [], "interfaces": {}}
    try:
        raw_payload = json.loads(HOST_NETWORK_FILE.read_text())
    except OSError as exc:
        msg = f"unable to read {HOST_NETWORK_FILE}: {exc}"
        raise ValueError(msg) from exc
    except json.JSONDecodeError as exc:
        msg = f"invalid JSON in {HOST_NETWORK_FILE}: {exc.msg}"
        raise ValueError(msg) from exc
    if not isinstance(raw_payload, dict):
        msg = f"{HOST_NETWORK_FILE} must contain a JSON object"
        raise ValueError(msg)

    payload = dict(raw_payload)
    require_host_keys(
        payload,
        {"dns_servers", "dns_search_domains", "default_gateway", "interfaces"},
        "host-network",
    )
    result: dict[str, object] = {
        "dns_servers": host_ip_list(payload, "dns_servers"),
        "dns_search_domains": host_search_domains(payload, "dns_search_domains"),
        "interfaces": {},
    }
    if "default_gateway" in payload:
        result["default_gateway"] = str(
            parse_host_ipv4_address(require_host_string(payload, "default_gateway"), "default_gateway")
        )

    interfaces = payload.get("interfaces", {})
    if not isinstance(interfaces, dict):
        msg = f"interfaces must be an object in {HOST_NETWORK_FILE}"
        raise ValueError(msg)
    normalized_interfaces: dict[str, dict[str, object]] = {}
    for name, value in interfaces.items():
        if not isinstance(name, str) or not HOST_INTERFACE_RE.fullmatch(name):
            msg = f"unsupported interface name in {HOST_NETWORK_FILE}: {name!r}"
            raise ValueError(msg)
        if not isinstance(value, dict):
            msg = f"interfaces.{name} must be an object in {HOST_NETWORK_FILE}"
            raise ValueError(msg)
        interface = dict(value)
        require_host_keys(
            interface,
            {"mode", "address", "gateway", "dns_servers", "dns_search_domains"},
            f"interfaces.{name}",
        )
        mode = require_host_string(interface, "mode")
        if mode not in {"dhcp", "static"}:
            msg = f"interfaces.{name}.mode must be dhcp or static in {HOST_NETWORK_FILE}"
            raise ValueError(msg)
        if name == LAN_INTERFACE and mode != "static":
            msg = f"interfaces.{name}.mode must be static because {name} is the LAN gateway in {HOST_NETWORK_FILE}"
            raise ValueError(msg)
        normalized: dict[str, object] = {"mode": mode}
        if mode == "static":
            normalized["address"] = str(
                parse_host_ipv4_interface(
                    require_host_string(interface, "address"), f"interfaces.{name}.address"
                )
            )
        elif "address" in interface:
            msg = f"interfaces.{name}.address is only supported for static mode in {HOST_NETWORK_FILE}"
            raise ValueError(msg)
        if "gateway" in interface:
            normalized["gateway"] = str(
                parse_host_ipv4_address(
                    require_host_string(interface, "gateway"), f"interfaces.{name}.gateway"
                )
            )
        if "dns_servers" in interface:
            normalized["dns_servers"] = [
                str(parse_ip_address(server, f"interfaces.{name}.dns_servers"))
                for server in host_string_list(interface, "dns_servers")
            ]
        if "dns_search_domains" in interface:
            normalized["dns_search_domains"] = [
                validate_host_dns_name(domain, f"interfaces.{name}.dns_search_domains")
                for domain in host_string_list(interface, "dns_search_domains")
            ]
        normalized_interfaces[name] = normalized
    result["interfaces"] = normalized_interfaces
    return result


def network_unit_name(interface: str) -> str:
    return f"30-atomixos-{interface}.network"


def network_config_path(interface: str) -> Path:
    if interface == "eth0":
        return ETH0_NETWORK_DROPIN
    if interface == LAN_INTERFACE:
        return NETWORK_FILE
    return HOST_NETWORK_CONFIG_DIR / network_unit_name(interface)


def render_domains(domains: list[str]) -> str:
    return " ".join(domains)


def render_interface_network(
    interface: str,
    settings: dict[str, object],
    host_settings: dict[str, object],
    lan_gateway_cidr: str | None = None,
) -> str:
    is_dropin = interface in {"eth0", LAN_INTERFACE}
    lines = [] if is_dropin else ["[Match]", f"Name={interface}", ""]
    lines.append("[Network]")
    mode = settings["mode"]
    if mode == "dhcp":
        lines.append("DHCP=ipv4")
        lines.append("IPv6AcceptRA=false")
    else:
        lines.append(f"Address={settings['address']}")
        lines.append("DHCP=no")
        lines.append("IPv6AcceptRA=false")
        if interface == LAN_INTERFACE and settings["address"] != lan_gateway_cidr:
            msg = (
                f"interfaces.{interface}.address must match gateway_cidr in "
                f"{CONFIG_FILE} and {HOST_NETWORK_FILE}"
            )
            raise ValueError(msg)
        if not is_dropin and interface == LAN_INTERFACE:
            lines.append("DHCPServer=false")
            lines.append("ConfigureWithoutCarrier=true")

    gateway = settings.get("gateway")
    if not gateway and interface == "eth0":
        gateway = host_settings.get("default_gateway")
    if gateway:
        lines.append(f"Gateway={gateway}")

    dns_servers = settings.get("dns_servers")
    if not dns_servers and interface == "eth0":
        dns_servers = host_settings.get("dns_servers", [])
    for server in dns_servers:
        lines.append(f"DNS={server}")
    domains = settings.get("dns_search_domains")
    if not domains and interface == "eth0":
        domains = host_settings.get("dns_search_domains", [])
    if domains:
        lines.append(f"Domains={render_domains(domains)}")
    dhcpv4_lines = []
    if gateway and mode == "dhcp":
        dhcpv4_lines.append("UseRoutes=false")
    if dns_servers and mode == "dhcp":
        dhcpv4_lines.append("UseDNS=false")
    if dhcpv4_lines:
        lines.extend(["", "[DHCPv4]", *dhcpv4_lines])
    return "\n".join(lines) + "\n"


def apply_host_network_settings(
    host_settings: dict[str, object], lan_gateway_cidr: str | None = None
) -> bool:
    planned = plan_host_network_settings(host_settings, lan_gateway_cidr)
    return apply_planned_host_network_settings(planned)


def apply_planned_host_network_settings(planned: dict[Path, str]) -> bool:
    changed = False
    desired_files = set(planned)
    for path, content in planned.items():
        changed = replace_file(path, content) or changed

    if ETH0_NETWORK_DROPIN.exists() and ETH0_NETWORK_DROPIN not in desired_files:
        ETH0_NETWORK_DROPIN.unlink()
        changed = True

    if HOST_NETWORK_CONFIG_DIR.exists():
        for existing in HOST_NETWORK_CONFIG_DIR.glob("30-atomixos-eth*.network"):
            if existing not in desired_files:
                existing.unlink()
                changed = True

    return changed


def plan_host_network_settings(
    host_settings: dict[str, object], lan_gateway_cidr: str | None = None
) -> dict[Path, str]:
    interfaces = host_settings.get("interfaces", {})
    if not isinstance(interfaces, dict):
        msg = f"interfaces must be an object in {HOST_NETWORK_FILE}"
        raise ValueError(msg)
    if (
        host_settings.get("default_gateway")
        or host_settings.get("dns_servers")
        or host_settings.get("dns_search_domains")
    ) and "eth0" not in interfaces:
        interfaces = {"eth0": {"mode": "dhcp"}, **interfaces}

    planned: dict[Path, str] = {}
    for name, settings in interfaces.items():
        if not isinstance(settings, dict):
            msg = f"interfaces.{name} must be an object in {HOST_NETWORK_FILE}"
            raise ValueError(msg)
        path = network_config_path(name)
        planned[path] = render_interface_network(name, settings, host_settings, lan_gateway_cidr)
    return planned


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
    payload["ntp_servers"] = ntp_servers(payload)

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
    host_settings = load_host_network_settings()

    gateway_cidr = payload["gateway_cidr"]
    gateway_ip = payload["gateway_ip"]
    subnet_cidr = payload["subnet_cidr"]
    netmask = payload["netmask"]
    dhcp_start = payload["dhcp_start"]
    dhcp_end = payload["dhcp_end"]
    domain = payload["domain"]
    aliases = payload.get("gateway_aliases", [])
    ntp_server_values = payload.get("ntp_servers", DEFAULT_NTP_SERVERS)
    hostname_pattern = payload.get("hostname_pattern", "")

    # Validate all host-network render decisions before mutating runtime files.
    planned_network_files = plan_host_network_settings(host_settings, gateway_cidr)
    planned_network_files.setdefault(NETWORK_FILE, "[Network]\n" f"Address={gateway_cidr}\n")

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
        "# Managed by lan-gateway-apply\n"
        + "".join(f"server {server} iburst\n" for server in ntp_server_values)
        + f"allow {subnet_cidr}\n",
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

    if apply_planned_host_network_settings(planned_network_files):
        run_command(["networkctl", "reload"])
        run_command(["systemctl", "try-restart", "systemd-networkd.service"])
        run_command(["systemctl", "try-restart", "systemd-resolved.service"])

    if dnsmasq_changed or dnsmasq_hosts_changed:
        run_command(["systemctl", "try-restart", "dnsmasq.service"])

    if chrony_changed:
        run_command(["systemctl", "try-restart", "chronyd.service"])

    apply_bootstrap_socket_rebind(gateway_ip)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"[lan-gateway-apply] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
