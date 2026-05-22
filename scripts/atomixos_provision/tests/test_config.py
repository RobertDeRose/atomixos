"""Tests for atomixos_provision.config module."""

from pathlib import Path

import pytest

from atomixos_provision.config import (
    ProvisionError,
    load_config,
    load_firewall_inbound,
    load_lan_settings,
    load_network_settings,
    load_users,
    require_allowed_keys,
    require_bool,
    require_dns_name,
    require_https_url,
    require_mapping,
    require_ntp_server_list,
    require_port_list,
    require_string,
    require_string_list,
    validate_against_schema,
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
        assert "myapp" in result["containers"]["container"]

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
