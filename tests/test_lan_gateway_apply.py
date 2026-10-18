import importlib.util
import json
from pathlib import Path

import pytest


def load_lan_gateway_apply():
    module_path = Path(__file__).resolve().parent.parent / "scripts" / "lan-gateway-apply.py"
    spec = importlib.util.spec_from_file_location("lan_gateway_apply", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def isolated_module(tmp_path, monkeypatch):
    """Load the script with every generated network path under tmp_path."""
    module = load_lan_gateway_apply()
    monkeypatch.setattr(module, "WAN_NETWORK_DROPIN", tmp_path / "10-wan.network.d" / "50-atomixos.conf")
    monkeypatch.setattr(module, "NETWORK_FILE", tmp_path / "20-lan.network.d" / "50-atomixos.conf")
    monkeypatch.setattr(module, "HOST_NETWORK_CONFIG_DIR", tmp_path / "network")
    return module


def test_host_network_rendering_is_idempotent(tmp_path, monkeypatch):
    module = isolated_module(tmp_path, monkeypatch)
    host_file = tmp_path / "host-network.json"
    wan_dropin = module.WAN_NETWORK_DROPIN
    lan_dropin = module.NETWORK_FILE
    host_file.write_text(
        json.dumps(
            {
                "dns_servers": ["1.1.1.1"],
                "dns_search_domains": ["lan.example"],
                "default_gateway": "192.0.2.1",
                "interfaces": {
                    "wan": {"mode": "dhcp"},
                    "lan": {
                        "mode": "static",
                        "address": "172.20.30.1/24",
                        "dns_servers": ["172.20.30.1"],
                        "dns_search_domains": ["lan"],
                    },
                },
            }
        )
    )
    monkeypatch.setattr(module, "HOST_NETWORK_FILE", host_file)

    settings = module.load_host_network_settings()
    assert module.apply_host_network_settings(settings, "172.20.30.1/24") is True
    assert wan_dropin.read_text() == (
        "[Network]\n"
        "DHCP=ipv4\n"
        "IPv6AcceptRA=false\n"
        "Gateway=192.0.2.1\n"
        "DNS=1.1.1.1\n"
        "Domains=lan.example\n"
        "\n"
        "[DHCPv4]\n"
        "UseRoutes=false\n"
        "UseDNS=false\n"
    )
    lan_network = lan_dropin.read_text()
    assert "Address=172.20.30.1/24\n" in lan_network
    assert "DHCP=no\n" in lan_network
    assert "Gateway=192.0.2.1\n" not in lan_network
    assert "DNS=172.20.30.1\n" in lan_network

    assert module.apply_host_network_settings(settings, "172.20.30.1/24") is False


def test_host_network_apply_removes_stale_managed_files(tmp_path, monkeypatch):
    module = isolated_module(tmp_path, monkeypatch)
    network_dir = module.HOST_NETWORK_CONFIG_DIR
    network_dir.mkdir()
    stale = network_dir / "30-atomixos-eth2.network"
    stale.write_text("stale\n")
    wan_dropin = module.WAN_NETWORK_DROPIN
    wan_dropin.parent.mkdir()
    wan_dropin.write_text("[Network]\nDNS=1.1.1.1\n")

    assert module.apply_host_network_settings(
        {"dns_servers": [], "dns_search_domains": [], "interfaces": {}}
    ) is True
    assert not stale.exists()
    assert not wan_dropin.exists()


def test_top_level_default_gateway_renders_wan_without_explicit_interface(tmp_path, monkeypatch):
    module = isolated_module(tmp_path, monkeypatch)
    wan_dropin = module.WAN_NETWORK_DROPIN

    assert module.apply_host_network_settings(
        {
            "dns_servers": [],
            "dns_search_domains": [],
            "default_gateway": "192.0.2.1",
            "interfaces": {},
        }
    ) is True
    wan_network = wan_dropin.read_text()
    assert "DHCP=ipv4\n" in wan_network
    assert "Gateway=192.0.2.1\n" in wan_network
    assert "UseRoutes=false\n" in wan_network


def test_static_wan_dropin_disables_dhcp(tmp_path, monkeypatch):
    module = isolated_module(tmp_path, monkeypatch)
    wan_dropin = module.WAN_NETWORK_DROPIN

    assert module.apply_host_network_settings(
        {
            "dns_servers": [],
            "dns_search_domains": [],
            "interfaces": {"wan": {"mode": "static", "address": "192.0.2.10/24"}},
        }
    ) is True
    assert wan_dropin.read_text() == (
        "[Network]\n"
        "Address=192.0.2.10/24\n"
        "DHCP=no\n"
        "IPv6AcceptRA=false\n"
    )


def test_top_level_dns_renders_wan_without_global_resolved_file(tmp_path, monkeypatch):
    module = isolated_module(tmp_path, monkeypatch)
    wan_dropin = module.WAN_NETWORK_DROPIN

    assert module.apply_host_network_settings(
        {
            "dns_servers": ["1.1.1.1"],
            "dns_search_domains": ["lan.example"],
            "interfaces": {},
        }
    ) is True
    wan_network = wan_dropin.read_text()
    assert "DNS=1.1.1.1\n" in wan_network
    assert "Domains=lan.example\n" in wan_network
    assert "UseDNS=false\n" in wan_network


def test_host_network_rejects_lan_dhcp(tmp_path, monkeypatch):
    module = isolated_module(tmp_path, monkeypatch)
    host_file = tmp_path / "host-network.json"
    host_file.write_text(json.dumps({"interfaces": {"lan": {"mode": "dhcp"}}}))
    monkeypatch.setattr(module, "HOST_NETWORK_FILE", host_file)

    with pytest.raises(ValueError, match="lan is the LAN gateway"):
        module.load_host_network_settings()


def test_host_network_rejects_unknown_keys_and_ipv6_gateways(tmp_path, monkeypatch):
    module = isolated_module(tmp_path, monkeypatch)
    host_file = tmp_path / "host-network.json"
    monkeypatch.setattr(module, "HOST_NETWORK_FILE", host_file)

    host_file.write_text(json.dumps({"bad": True}))
    with pytest.raises(ValueError, match="unsupported keys at host-network"):
        module.load_host_network_settings()


def test_host_network_apply_rejects_lan_mismatch(tmp_path, monkeypatch):
    module = isolated_module(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match=r"interfaces\.lan\.address must match gateway_cidr"):
        module.apply_host_network_settings(
            {
                "dns_servers": [],
                "dns_search_domains": [],
                "interfaces": {"lan": {"mode": "static", "address": "10.0.0.1/24"}},
            },
            "172.20.30.1/24",
        )


def test_host_network_rejects_unknown_keys_and_invalid_values(tmp_path, monkeypatch):
    module = isolated_module(tmp_path, monkeypatch)
    host_file = tmp_path / "host-network.json"
    monkeypatch.setattr(module, "HOST_NETWORK_FILE", host_file)

    host_file.write_text(json.dumps({"default_gateway": "2001:db8::1"}))
    with pytest.raises(ValueError, match="default_gateway must be a valid IPv4 address"):
        module.load_host_network_settings()

    host_file.write_text(json.dumps({"interfaces": {"wan": {"mode": "dhcp", "mtu": 1500}}}))
    with pytest.raises(ValueError, match=r"unsupported keys at interfaces\.wan"):
        module.load_host_network_settings()

    host_file.write_text(json.dumps({"dns_search_domains": ["bad/domain"]}))
    with pytest.raises(ValueError, match="dns_search_domains must be a valid DNS name"):
        module.load_host_network_settings()

    host_file.write_text(json.dumps({"interfaces": {"eth2": {"mode": "static", "address": "bad"}}}))
    with pytest.raises(
        ValueError, match=r"interfaces\.eth2\.address must be a valid IPv4 interface"
    ):
        module.load_host_network_settings()


def test_dnsmasq_rendering_remains_gateway_local(tmp_path, monkeypatch):
    module = isolated_module(tmp_path, monkeypatch)
    dnsmasq_dir = tmp_path / "dnsmasq.d"
    hosts_file = tmp_path / "dnsmasq-hosts"
    chrony_file = tmp_path / "chrony-lan.conf"
    etc_hosts = tmp_path / "hosts"
    sys_net = tmp_path / "sys" / "class" / "net" / "lan"
    sys_net.mkdir(parents=True)
    (sys_net / "address").write_text("00:11:22:33:44:55\n")
    settings_file = tmp_path / "lan-settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "gateway_cidr": "10.44.0.1/24",
                "gateway_ip": "10.44.0.1",
                "subnet_cidr": "10.44.0.0/24",
                "netmask": "255.255.255.0",
                "dhcp_start": "10.44.0.10",
                "dhcp_end": "10.44.0.200",
                "domain": "lab",
                "hostname_pattern": "gateway-{mac}",
                "gateway_aliases": ["atomixos"],
                "ntp_servers": ["time.cloudflare.com"],
            }
        )
    )
    monkeypatch.setattr(module, "CONFIG_FILE", settings_file)
    monkeypatch.setattr(module, "HOST_NETWORK_FILE", tmp_path / "missing-host-network.json")
    monkeypatch.setattr(module, "DNSMASQ_CONFIG_DIR", dnsmasq_dir)
    monkeypatch.setattr(module, "DNSMASQ_CONFIG_FILE", dnsmasq_dir / "atomixos-lan.conf")
    monkeypatch.setattr(module, "DNSMASQ_HOSTS_FILE", hosts_file)
    monkeypatch.setattr(module, "CHRONY_LAN_FILE", chrony_file)
    monkeypatch.setattr(module, "ETC_HOSTS_FILE", etc_hosts)
    monkeypatch.setattr(module, "SYS_CLASS_NET_DIR", tmp_path / "sys" / "class" / "net")
    monkeypatch.setattr(module, "apply_bootstrap_socket_rebind", lambda _gateway_ip: None)
    monkeypatch.setattr(module, "run_command", lambda _args: None)

    module.main()

    dnsmasq = (dnsmasq_dir / "atomixos-lan.conf").read_text()
    assert "local=/lab/\n" in dnsmasq
    assert "server=" not in dnsmasq
    assert "resolv-file=" not in dnsmasq


def test_main_is_idempotent_with_host_network_lan(tmp_path, monkeypatch):
    module = isolated_module(tmp_path, monkeypatch)
    settings_file = tmp_path / "lan-settings.json"
    network_file = module.NETWORK_FILE
    host_file = tmp_path / "host-network.json"
    settings_file.write_text(
        json.dumps(
            {
                "gateway_cidr": "172.20.30.1/24",
                "gateway_ip": "172.20.30.1",
                "subnet_cidr": "172.20.30.0/24",
                "netmask": "255.255.255.0",
                "dhcp_start": "172.20.30.10",
                "dhcp_end": "172.20.30.254",
                "domain": "local",
                "gateway_aliases": ["atomixos"],
            }
        )
    )
    host_file.write_text(
        json.dumps(
            {
                "interfaces": {
                    "lan": {
                        "mode": "static",
                        "address": "172.20.30.1/24",
                        "dns_servers": ["172.20.30.1"],
                    }
                }
            }
        )
    )
    monkeypatch.setattr(module, "CONFIG_FILE", settings_file)
    monkeypatch.setattr(module, "HOST_NETWORK_FILE", host_file)
    monkeypatch.setattr(module, "DNSMASQ_CONFIG_FILE", tmp_path / "dnsmasq.d" / "atomixos-lan.conf")
    monkeypatch.setattr(module, "DNSMASQ_HOSTS_FILE", tmp_path / "dnsmasq-hosts")
    monkeypatch.setattr(module, "CHRONY_LAN_FILE", tmp_path / "chrony-lan.conf")
    monkeypatch.setattr(module, "ETC_HOSTS_FILE", tmp_path / "hosts")
    monkeypatch.setattr(module, "apply_bootstrap_socket_rebind", lambda _gateway_ip: None)
    commands = []
    monkeypatch.setattr(module, "run_command", commands.append)

    module.main()
    first_render = network_file.read_text()
    first_commands = list(commands)
    commands.clear()

    module.main()

    assert network_file.read_text() == first_render
    assert "DNS=172.20.30.1\n" in first_render
    assert first_commands.count(["systemctl", "try-restart", "systemd-networkd.service"]) == 1
    assert ["systemctl", "try-restart", "systemd-networkd.service"] not in commands


def test_host_network_preflight_fails_before_mutation(tmp_path, monkeypatch):
    module = isolated_module(tmp_path, monkeypatch)
    settings_file = tmp_path / "lan-settings.json"
    network_file = module.NETWORK_FILE
    host_file = tmp_path / "host-network.json"
    settings_file.write_text(
        json.dumps(
            {
                "gateway_cidr": "172.20.30.1/24",
                "gateway_ip": "172.20.30.1",
                "subnet_cidr": "172.20.30.0/24",
                "netmask": "255.255.255.0",
                "dhcp_start": "172.20.30.10",
                "dhcp_end": "172.20.30.254",
                "domain": "local",
                "gateway_aliases": ["atomixos"],
            }
        )
    )
    host_file.write_text(
        json.dumps({"interfaces": {"lan": {"mode": "static", "address": "10.0.0.1/24"}}})
    )
    monkeypatch.setattr(module, "CONFIG_FILE", settings_file)
    monkeypatch.setattr(module, "HOST_NETWORK_FILE", host_file)

    with pytest.raises(ValueError, match=r"interfaces\.lan\.address must match gateway_cidr"):
        module.main()

    assert not network_file.exists()


def test_lan_settings_invalid_cidr_reports_file_and_key(tmp_path, monkeypatch):
    module = isolated_module(tmp_path, monkeypatch)
    settings_file = tmp_path / "lan-settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "gateway_cidr": "172.20.30.1/33",
                "gateway_ip": "172.20.30.1",
                "subnet_cidr": "172.20.30.0/24",
                "netmask": "255.255.255.0",
                "dhcp_start": "172.20.30.10",
                "dhcp_end": "172.20.30.254",
                "domain": "local",
                "gateway_aliases": ["atomixos"],
            }
        )
    )
    monkeypatch.setattr(module, "CONFIG_FILE", settings_file)

    with pytest.raises(ValueError, match=f"gateway_cidr must be a valid IPv4 interface in {settings_file}"):
        module.load_settings()


def test_extra_ethernet_interface_renders_standalone_unit(tmp_path, monkeypatch):
    module = isolated_module(tmp_path, monkeypatch)

    assert module.apply_host_network_settings(
        {
            "dns_servers": [],
            "dns_search_domains": [],
            "interfaces": {
                "eth2": {"mode": "static", "address": "198.51.100.5/24", "dns_servers": ["198.51.100.1"]}
            },
        }
    ) is True
    unit = (module.HOST_NETWORK_CONFIG_DIR / "30-atomixos-eth2.network").read_text()
    assert unit.startswith("[Match]\nName=eth2\n")
    assert "Address=198.51.100.5/24\n" in unit


def test_qemu_physical_names_map_to_logical_dropins(tmp_path, monkeypatch):
    # QEMU keeps the kernel names, so WAN and LAN are physically eth0 and eth1.
    module = isolated_module(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "WAN_INTERFACE", "eth0")
    monkeypatch.setattr(module, "LAN_INTERFACE", "eth1")
    host_file = tmp_path / "host-network.json"
    monkeypatch.setattr(module, "HOST_NETWORK_FILE", host_file)

    host_file.write_text(json.dumps({"interfaces": {"wan": {"mode": "static", "address": "192.0.2.10/24"}}}))
    assert module.apply_host_network_settings(module.load_host_network_settings()) is True
    assert "Address=192.0.2.10/24\n" in module.WAN_NETWORK_DROPIN.read_text()
    assert not module.HOST_NETWORK_CONFIG_DIR.exists()

    for alias in ("eth0", "eth1"):
        host_file.write_text(json.dumps({"interfaces": {alias: {"mode": "dhcp"}}}))
        with pytest.raises(ValueError, match=rf"interfaces\.{alias} is the WAN or LAN interface"):
            module.load_host_network_settings()
