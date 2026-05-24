"""Tests for atomixos_provision.config module."""

from pathlib import Path

import pytest

from atomixos_provision.config import (
    ProvisionError,
    load_config,
    load_firewall_inbound,
    load_host_network_settings,
    load_lan_settings,
    load_network_interfaces,
    load_network_settings,
    load_users,
    require_allowed_keys,
    require_bool,
    require_dns_name,
    require_dns_search_domains,
    require_https_url,
    require_ip_address,
    require_ip_address_list,
    require_ipv4_address,
    require_mapping,
    require_ntp_server_list,
    require_port_list,
    require_string,
    require_string_list,
    validate_against_schema,
    validate_interface_name,
    validate_name,
    validate_username,
)

VALID_ED25519_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAw"
)

# --- Fixtures ---


@pytest.fixture()
def schema_path(tmp_path: Path) -> Path:
    """Locate the real schema file and copy it for test use."""
    repo_schema = (
        Path(__file__).resolve().parent.parent.parent.parent / "schemas" / "config.schema.json"
    )
    if not repo_schema.exists():
        pytest.skip("config.schema.json not found in repo; cannot run schema tests")
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    schema_file = schema_dir / "config.schema.json"
    schema_file.write_text(repo_schema.read_text())
    return schema_file


@pytest.fixture()
def minimal_config_toml(tmp_path: Path) -> Path:
    """Create a minimal valid config.toml."""
    config = tmp_path / "config.toml"
    config.write_text(
        f"""\
version = 1

[users.admin]
isAdmin = true
ssh_key = "{VALID_ED25519_KEY} test@test"

[activation]
required = ["myapp"]

[containers.container.myapp]
privileged = false

[containers.container.myapp.Container]
Image = "docker.io/library/alpine:latest"
"""
    )
    return config


# --- Validation Helper Tests ---


class TestRequireMapping:
    def test_valid(self):
        assert require_mapping({"a": 1}, "test") == {"a": 1}

    def test_invalid(self):
        with pytest.raises(ProvisionError, match="expected table at test"):
            require_mapping("not a dict", "test")


class TestRequireAllowedKeys:
    def test_valid(self):
        result = require_allowed_keys({"a": 1}, "t", {"a", "b"})
        assert result == {"a": 1}

    def test_unexpected_key(self):
        with pytest.raises(ProvisionError, match="unsupported keys"):
            require_allowed_keys({"a": 1, "c": 2}, "t", {"a", "b"})

    def test_missing_required(self):
        with pytest.raises(ProvisionError, match="missing required keys"):
            require_allowed_keys({"a": 1}, "t", {"a", "b"}, {"a", "b"})


class TestRequireString:
    def test_valid(self):
        assert require_string("hello", "t") == "hello"

    def test_strips(self):
        assert require_string("  hello  ", "t") == "hello"

    def test_empty(self):
        with pytest.raises(ProvisionError):
            require_string("", "t")

    def test_not_string(self):
        with pytest.raises(ProvisionError):
            require_string(123, "t")


class TestRequireStringList:
    def test_valid(self):
        assert require_string_list(["a", "b"], "t") == ["a", "b"]

    def test_empty_list(self):
        with pytest.raises(ProvisionError):
            require_string_list([], "t")

    def test_not_list(self):
        with pytest.raises(ProvisionError):
            require_string_list("not a list", "t")


class TestRequireBool:
    def test_valid(self):
        assert require_bool(True, "t") is True
        assert require_bool(False, "t") is False

    def test_invalid(self):
        with pytest.raises(ProvisionError):
            require_bool(1, "t")


class TestRequirePortList:
    def test_valid(self):
        assert require_port_list([80, 443], "t") == [80, 443]

    def test_invalid_range(self):
        with pytest.raises(ProvisionError):
            require_port_list([0], "t")

    def test_invalid_type(self):
        with pytest.raises(ProvisionError):
            require_port_list([True], "t")


class TestRequireDnsName:
    def test_valid(self):
        assert require_dns_name("example.com", "t") == "example.com"

    def test_strips_trailing_dot(self):
        assert require_dns_name("example.com.", "t") == "example.com"

    def test_invalid_chars(self):
        with pytest.raises(ProvisionError, match="invalid DNS name"):
            require_dns_name("exam ple.com", "t")

    def test_rejects_unicode(self):
        with pytest.raises(ProvisionError, match="invalid DNS name"):
            require_dns_name("tést.example", "t")

    def test_rejects_overlong_name(self):
        name = ".".join(["a" * 63, "b" * 63, "c" * 63, "d" * 63])
        with pytest.raises(ProvisionError, match="longer than 253"):
            require_dns_name(name, "t")


class TestRequireNtpServerList:
    def test_accepts_dns_and_ip_literals(self):
        servers = require_ntp_server_list(["time.example.com", "192.0.2.1", "2001:db8::1"], "ntp")
        assert servers == ["time.example.com", "192.0.2.1", "2001:db8::1"]

    def test_rejects_invalid_hostname(self):
        with pytest.raises(ProvisionError, match="invalid DNS name"):
            require_ntp_server_list(["bad/name"], "ntp")


class TestNetworkValidationHelpers:
    def test_require_ip_address(self):
        assert require_ip_address("192.0.2.1", "network.default_gateway") == "192.0.2.1"
        assert require_ip_address("2001:db8::1", "network.default_gateway") == "2001:db8::1"

    def test_require_ipv4_address(self):
        assert require_ipv4_address("192.0.2.1", "network.default_gateway") == "192.0.2.1"
        with pytest.raises(ProvisionError, match="invalid IPv4 address"):
            require_ipv4_address("2001:db8::1", "network.default_gateway")

    def test_require_ip_address_rejects_invalid_and_empty(self):
        with pytest.raises(ProvisionError, match="invalid IP address"):
            require_ip_address("not-an-ip", "network.default_gateway")
        with pytest.raises(ProvisionError, match="expected non-empty string"):
            require_ip_address("", "network.default_gateway")

    def test_require_ip_address_list(self):
        assert require_ip_address_list(["1.1.1.1", "2001:db8::1"], "network.dns_servers") == [
            "1.1.1.1",
            "2001:db8::1",
        ]

    def test_require_dns_search_domains(self):
        assert require_dns_search_domains(
            ["LAN.Example.", "site.local"], "network.dns_search_domains"
        ) == ["lan.example", "site.local"]

    def test_validate_interface_name(self):
        assert validate_interface_name("eth0") == "eth0"
        assert validate_interface_name("eth12") == "eth12"
        with pytest.raises(ProvisionError, match="unsupported network interface name"):
            validate_interface_name("wlan0")
        with pytest.raises(ProvisionError, match="unsupported network interface name"):
            validate_interface_name("eth0/../../bad")


class TestRequireHttpsUrl:
    def test_accepts_https_base_url(self):
        assert (
            require_https_url("https://updates.example.com/base/", "url")
            == "https://updates.example.com/base"
        )

    def test_rejects_query_and_fragment(self):
        with pytest.raises(ProvisionError, match="query string or fragment"):
            require_https_url("https://updates.example.com?tenant=x", "url")
        with pytest.raises(ProvisionError, match="query string or fragment"):
            require_https_url("https://updates.example.com/#latest", "url")

    def test_rejects_whitespace(self):
        with pytest.raises(ProvisionError, match="whitespace/control"):
            require_https_url("https://updates.example.com/bad path", "url")

    def test_rejects_invalid_host(self):
        with pytest.raises(ProvisionError, match="invalid DNS name"):
            require_https_url("https://bad_host.example", "url")


class TestValidateName:
    def test_valid(self):
        assert validate_name("my-app") == "my-app"
        assert validate_name("app_1") == "app_1"

    def test_empty(self):
        with pytest.raises(ProvisionError):
            validate_name("")

    def test_with_dot(self):
        with pytest.raises(ProvisionError):
            validate_name("my.app")

    def test_with_slash(self):
        with pytest.raises(ProvisionError):
            validate_name("my/app")

    def test_starts_with_dash(self):
        with pytest.raises(ProvisionError):
            validate_name("-app")


class TestValidateUsername:
    def test_valid(self):
        assert validate_username("admin") == "admin"

    def test_reserved(self):
        with pytest.raises(ProvisionError, match="reserved user name"):
            validate_username("root")

    def test_invalid_format(self):
        with pytest.raises(ProvisionError, match="invalid user name"):
            validate_username("Admin")  # uppercase not allowed


# --- Section Loader Tests ---


class TestLoadUsers:
    def test_valid(self):
        users, keys = load_users(
            {
                "admin": {"isAdmin": True, "ssh_key": VALID_ED25519_KEY},
            }
        )
        assert users["admin"]["isAdmin"] is True
        assert keys == [VALID_ED25519_KEY]

    def test_shell(self):
        users, _ = load_users(
            {
                "admin": {
                    "isAdmin": True,
                    "ssh_key": VALID_ED25519_KEY,
                    "shell": "bash",
                },
            }
        )
        assert users["admin"]["shell"] == "bash"

    def test_invalid_shell(self):
        with pytest.raises(ProvisionError, match="shell must be one of"):
            load_users(
                {
                    "admin": {
                        "isAdmin": True,
                        "ssh_key": VALID_ED25519_KEY,
                        "shell": "/bin/bash",
                    },
                }
            )

    def test_no_admin_key(self):
        with pytest.raises(ProvisionError, match="at least one admin"):
            load_users({"user1": {"isAdmin": False}})


class TestLoadLanSettings:
    def test_defaults(self):
        result = load_lan_settings({})
        assert result["gateway_ip"] == "172.20.30.1"
        assert result["dhcp_start"] == "172.20.30.10"
        assert result["dhcp_end"] == "172.20.30.254"

    def test_invalid_cidr(self):
        with pytest.raises(ProvisionError, match="invalid IPv4 CIDR"):
            load_lan_settings({"gateway_cidr": "not-an-ip"})

    def test_prefix_out_of_range(self):
        with pytest.raises(ProvisionError, match="between /16 and /30"):
            load_lan_settings({"gateway_cidr": "10.0.0.1/8"})
        with pytest.raises(ProvisionError, match="between /16 and /30"):
            load_lan_settings({"gateway_cidr": "10.0.0.1/31"})


class TestLoadFirewallInbound:
    def test_empty(self):
        assert load_firewall_inbound(None) == {}

    def test_with_ports(self):
        result = load_firewall_inbound({"firewall": {"inbound": {"wan": {"tcp": [80, 443]}}}})
        assert result == {"wan": {"tcp": [80, 443]}}

    def test_rejects_reserved_wan_bootstrap_port(self):
        with pytest.raises(ProvisionError, match="reserved bootstrap port 8080"):
            load_firewall_inbound({"firewall": {"inbound": {"wan": {"tcp": [8080]}}}})

    def test_drops_explicit_empty_lan_scope(self):
        result = load_firewall_inbound({"firewall": {"inbound": {"lan": {"tcp": [], "udp": []}}}})
        assert result == {}


class TestLoadNetworkSettings:
    def test_defaults(self):
        result = load_network_settings(None)
        assert result["gateway_ip"] == "172.20.30.1"
        assert result["ntp_servers"] == ["time.cloudflare.com"]

    def test_reconciles_eth1_address_with_dnsmasq_gateway(self):
        result = load_network_settings(
            {
                "interfaces": {"eth1": {"mode": "static", "address": "10.50.0.1/24"}},
                "dnsmasq": {"dhcp_start": "10.50.0.10", "dhcp_end": "10.50.0.254"},
            }
        )
        assert result["gateway_cidr"] == "10.50.0.1/24"
        assert result["gateway_ip"] == "10.50.0.1"

    def test_reconciles_equivalent_eth1_and_dnsmasq_gateway_values(self):
        result = load_network_settings(
            {
                "interfaces": {"eth1": {"mode": "static", "address": " 10.50.0.1/24 "}},
                "dnsmasq": {
                    "gateway_cidr": "10.50.0.1/24",
                    "dhcp_start": "10.50.0.10",
                    "dhcp_end": "10.50.0.254",
                },
            }
        )
        assert result["gateway_cidr"] == "10.50.0.1/24"

    def test_rejects_conflicting_eth1_address_and_dnsmasq_gateway(self):
        with pytest.raises(ProvisionError, match=r"must match network\.dnsmasq\.gateway_cidr"):
            load_network_settings(
                {
                    "interfaces": {"eth1": {"mode": "static", "address": "10.50.0.1/24"}},
                    "dnsmasq": {
                        "gateway_cidr": "10.51.0.1/24",
                        "dhcp_start": "10.51.0.10",
                        "dhcp_end": "10.51.0.254",
                    },
                }
            )


class TestLoadHostNetworkSettings:
    def test_defaults_omit_default_gateway(self):
        assert load_host_network_settings(None) == {
            "dns_servers": [],
            "dns_search_domains": [],
            "interfaces": {},
        }

    def test_top_level_host_network_settings(self):
        assert load_host_network_settings(
            {
                "dns_servers": ["1.1.1.1", "9.9.9.9"],
                "dns_search_domains": ["LAN.Example"],
                "default_gateway": "192.0.2.1",
            }
        ) == {
            "dns_servers": ["1.1.1.1", "9.9.9.9"],
            "dns_search_domains": ["lan.example"],
            "interfaces": {},
            "default_gateway": "192.0.2.1",
        }

    def test_rejects_invalid_default_gateway(self):
        with pytest.raises(
            ProvisionError, match=r"invalid IPv4 address at network\.default_gateway"
        ):
            load_host_network_settings({"default_gateway": "not-an-ip"})

    def test_rejects_ipv6_default_gateway(self):
        with pytest.raises(
            ProvisionError, match=r"invalid IPv4 address at network\.default_gateway"
        ):
            load_host_network_settings({"default_gateway": "2001:db8::1"})

    def test_rejects_empty_default_gateway_sentinel(self):
        with pytest.raises(ProvisionError, match="expected non-empty string"):
            load_host_network_settings({"default_gateway": ""})

    def test_rejects_invalid_dns_server(self):
        with pytest.raises(
            ProvisionError, match=r"invalid IP address at network\.dns_servers\[0\]"
        ):
            load_host_network_settings({"dns_servers": ["bad"]})

    def test_rejects_invalid_search_domain(self):
        with pytest.raises(
            ProvisionError, match=r"invalid DNS name at network\.dns_search_domains\[0\]"
        ):
            load_host_network_settings({"dns_search_domains": ["bad/domain"]})

    def test_rejects_unknown_network_key(self):
        with pytest.raises(ProvisionError, match="unsupported keys at network: bad"):
            load_host_network_settings({"bad": True})


class TestLoadNetworkInterfaces:
    def test_dhcp_interface(self):
        assert load_network_interfaces({"eth0": {"mode": "dhcp"}}) == {"eth0": {"mode": "dhcp"}}

    def test_static_interface(self):
        assert load_network_interfaces(
            {
                "eth1": {
                    "mode": "static",
                    "address": "172.20.30.1/24",
                    "gateway": "172.20.30.254",
                    "dns_servers": ["172.20.30.1"],
                    "dns_search_domains": ["lan"],
                }
            }
        ) == {
            "eth1": {
                "mode": "static",
                "address": "172.20.30.1/24",
                "gateway": "172.20.30.254",
                "dns_servers": ["172.20.30.1"],
                "dns_search_domains": ["lan"],
            }
        }

    def test_static_requires_address(self):
        with pytest.raises(
            ProvisionError, match=r"missing required keys at network\.interfaces\.eth1: address"
        ):
            load_network_interfaces({"eth1": {"mode": "static"}})

    def test_dhcp_rejects_address(self):
        with pytest.raises(ProvisionError, match="address is only supported when mode is static"):
            load_network_interfaces({"eth0": {"mode": "dhcp", "address": "192.0.2.10/24"}})

    def test_rejects_invalid_mode(self):
        with pytest.raises(ProvisionError, match="mode must be one of: dhcp, static"):
            load_network_interfaces({"eth0": {"mode": "manual"}})

    def test_rejects_invalid_static_cidr(self):
        with pytest.raises(
            ProvisionError, match=r"invalid IPv4 CIDR at network\.interfaces\.eth1\.address"
        ):
            load_network_interfaces({"eth1": {"mode": "static", "address": "not-a-cidr"}})

    def test_rejects_unknown_interface_key(self):
        with pytest.raises(
            ProvisionError, match=r"unsupported keys at network\.interfaces\.eth0: mtu"
        ):
            load_network_interfaces({"eth0": {"mode": "dhcp", "mtu": 1500}})

    def test_rejects_empty_gateway_sentinel(self):
        with pytest.raises(ProvisionError, match="expected non-empty string"):
            load_network_interfaces(
                {"eth1": {"mode": "static", "address": "172.20.30.1/24", "gateway": ""}}
            )

    def test_rejects_wifi_interface(self):
        with pytest.raises(ProvisionError, match="unsupported network interface name"):
            load_network_interfaces({"wlan0": {"mode": "dhcp"}})

    def test_rejects_eth1_dhcp(self):
        with pytest.raises(ProvisionError, match="eth1 is the LAN gateway"):
            load_network_interfaces({"eth1": {"mode": "dhcp"}})


# --- Schema Validation Tests ---


class TestValidateAgainstSchema:
    def test_type_check(self):
        schema = {"type": "string"}
        validate_against_schema("hello", schema, "t", schema)

    def test_type_mismatch(self):
        schema = {"type": "string"}
        with pytest.raises(ProvisionError, match="expected string"):
            validate_against_schema(123, schema, "t", schema)

    def test_enum(self):
        schema = {"type": "integer", "enum": [1]}
        validate_against_schema(1, schema, "t", schema)
        with pytest.raises(ProvisionError, match="unexpected value"):
            validate_against_schema(2, schema, "t", schema)

    def test_required_keys(self):
        schema = {"type": "object", "required": ["a"]}
        with pytest.raises(ProvisionError, match="missing required keys"):
            validate_against_schema({}, schema, "t", schema)


# --- Integration: load_config ---


class TestLoadConfig:
    def test_minimal_valid(self, minimal_config_toml: Path, schema_path: Path, monkeypatch):
        monkeypatch.setenv("ATOMIXOS_CONFIG_SCHEMA", str(schema_path))
        result = load_config(minimal_config_toml)
        assert result["users"]["admin"]["isAdmin"] is True
        assert result["ssh_keys"] == [f"{VALID_ED25519_KEY} test@test"]
        assert result["required_units"] == ["myapp"]
        assert result["activation_policy"] == {
            "required": ["myapp"],
            "timeout_seconds": 300,
            "settle_seconds": 0,
            "restart": [],
            "allow_degraded": [],
            "allow_degraded_configured": False,
            "strategy": "rollback",
        }
        assert "myapp" in result["containers"]["container"]

    def test_activation_options_valid(self, tmp_path: Path, schema_path: Path, monkeypatch):
        monkeypatch.setenv("ATOMIXOS_CONFIG_SCHEMA", str(schema_path))
        config = tmp_path / "config.toml"
        config.write_text(
            f"""\
version = 1

[users.admin]
isAdmin = true
ssh_key = "{VALID_ED25519_KEY} test@test"

[activation]
required = ["myapp"]
timeout_seconds = 120
settle_seconds = 5
restart = ["myapp"]
allow_degraded = ["sidecar"]
strategy = "rollback"

[containers.container.myapp]
privileged = false

[containers.container.myapp.Container]
Image = "docker.io/library/alpine:latest"

[containers.container.sidecar]
privileged = false

[containers.container.sidecar.Container]
Image = "docker.io/library/alpine:latest"
"""
        )
        result = load_config(config)
        assert result["activation_policy"] == {
            "required": ["myapp"],
            "timeout_seconds": 120,
            "settle_seconds": 5,
            "restart": ["myapp"],
            "allow_degraded": ["sidecar"],
            "allow_degraded_configured": True,
            "strategy": "rollback",
        }

    @pytest.mark.parametrize(
        ("activation_snippet", "error"),
        [
            ('required = ["myapp"]\ntimeout_seconds = 0', "activation.timeout_seconds"),
            ('required = ["myapp"]\ntimeout_seconds = 3601', "activation.timeout_seconds"),
            ('required = ["myapp"]\nsettle_seconds = -1', "activation.settle_seconds"),
            ('required = ["myapp"]\nsettle_seconds = 301', "activation.settle_seconds"),
            ('required = ["missing"]', "activation.required references unknown unit: missing"),
            (
                'required = ["myapp"]\nrestart = ["missing"]',
                "activation.restart references unknown unit: missing",
            ),
            (
                'required = ["myapp"]\nallow_degraded = ["missing"]',
                "activation.allow_degraded references unknown unit: missing",
            ),
            (
                'required = ["myapp"]\nallow_degraded = ["myapp"]',
                "allow_degraded must not include required units",
            ),
            ('required = ["myapp"]\nstrategy = "keep-failed"', "activation.strategy"),
            ('required = ["myapp"]\nstrategy = "manual-confirm"', "activation.strategy"),
        ],
    )
    def test_activation_options_invalid(
        self, tmp_path: Path, schema_path: Path, monkeypatch, activation_snippet: str, error: str
    ):
        monkeypatch.setenv("ATOMIXOS_CONFIG_SCHEMA", str(schema_path))
        config = tmp_path / "config.toml"
        config.write_text(
            f"""\
version = 1

[users.admin]
isAdmin = true
ssh_key = "{VALID_ED25519_KEY} test@test"

[activation]
{activation_snippet}

[containers.container.myapp]
privileged = false

[containers.container.myapp.Container]
Image = "docker.io/library/alpine:latest"
"""
        )
        with pytest.raises(ProvisionError, match=error):
            load_config(config)

    def test_network_extensions_valid(self, tmp_path: Path, schema_path: Path, monkeypatch):
        monkeypatch.setenv("ATOMIXOS_CONFIG_SCHEMA", str(schema_path))
        config = tmp_path / "config.toml"
        config.write_text(
            f"""\
version = 1

[users.admin]
isAdmin = true
ssh_key = "{VALID_ED25519_KEY} test@test"

[network]
dns_servers = ["1.1.1.1"]
dns_search_domains = ["lan.example"]
default_gateway = "192.0.2.1"

[network.interfaces.eth0]
mode = "dhcp"

[network.interfaces.eth1]
mode = "static"
address = "172.20.30.1/24"
dns_servers = ["172.20.30.1"]
dns_search_domains = ["lan"]

[activation]
required = ["myapp"]

[containers.container.myapp]
privileged = false

[containers.container.myapp.Container]
Image = "docker.io/library/alpine:latest"
"""
        )
        result = load_config(config)
        assert result["host_network"]["default_gateway"] == "192.0.2.1"
        assert result["host_network"]["interfaces"]["eth1"]["dns_servers"] == ["172.20.30.1"]

    def test_invalid_toml(self, tmp_path: Path, schema_path: Path, monkeypatch):
        monkeypatch.setenv("ATOMIXOS_CONFIG_SCHEMA", str(schema_path))
        bad = tmp_path / "bad.toml"
        bad.write_text("not valid [[[toml")
        with pytest.raises(ProvisionError, match="invalid TOML"):
            load_config(bad)

    def test_rejects_non_current_version(self, tmp_path: Path, schema_path: Path, monkeypatch):
        monkeypatch.setenv("ATOMIXOS_CONFIG_SCHEMA", str(schema_path))
        config = tmp_path / "config.toml"
        config.write_text(
            f"""\
version = 2

[users.admin]
isAdmin = true
ssh_key = "{VALID_ED25519_KEY} test"

[activation]
required = ["app"]

[containers.container.app]
privileged = false

[containers.container.app.Container]
Image = "alpine"
"""
        )
        with pytest.raises(ProvisionError, match="version must be integer 1"):
            load_config(config)
