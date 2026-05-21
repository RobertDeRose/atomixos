"""Tests for atomixos_provision.config_builder module."""


import pytest

from atomixos_provision.config import ProvisionError
from atomixos_provision.config_builder import (
    build_config_from_form,
    generated_extra_users,
    generated_required_units,
    parse_port_lines,
)


class TestParsePortLines:
    def test_valid(self):
        assert parse_port_lines("80\n443\n", "test") == [80, 443]

    def test_empty(self):
        assert parse_port_lines("", "test") == []

    def test_skips_blank_lines(self):
        assert parse_port_lines("80\n\n443\n", "test") == [80, 443]

    def test_invalid_number(self):
        with pytest.raises(ProvisionError, match="not a valid port"):
            parse_port_lines("abc", "test")

    def test_out_of_range(self):
        with pytest.raises(ProvisionError, match="out of range"):
            parse_port_lines("99999", "test")

    def test_zero(self):
        with pytest.raises(ProvisionError, match="out of range"):
            parse_port_lines("0", "test")


class TestGeneratedRequiredUnits:
    def test_valid_snippet(self):
        snippet = """\
[container.myapp]
privileged = false

[container.myapp.Container]
Image = "alpine"
"""
        assert generated_required_units(snippet) == ["myapp"]

    def test_empty_snippet(self):
        with pytest.raises(ProvisionError, match="container TOML snippet is required"):
            generated_required_units("")

    def test_invalid_toml(self):
        with pytest.raises(ProvisionError, match="invalid container TOML"):
            generated_required_units("[[[bad")

    def test_no_container_table(self):
        with pytest.raises(ProvisionError, match="must define at least one"):
            generated_required_units("[something]\nfoo = 1\n")


class TestGeneratedExtraUsers:
    def test_empty(self):
        assert generated_extra_users([]) == ""

    def test_one_extra(self):
        result = generated_extra_users(["ssh-ed25519 AAAA key2"])
        assert "[users.admin2]" in result
        assert "ssh-ed25519 AAAA key2" in result

    def test_multiple(self):
        result = generated_extra_users(["key2", "key3"])
        assert "[users.admin2]" in result
        assert "[users.admin3]" in result


class TestBuildConfigFromForm:
    def test_minimal(self):
        form = {
            "ssh_keys": "ssh-ed25519 AAAA test@test",
            "quadlet": (
                "[container.myapp]\nprivileged = false\n\n"
                "[container.myapp.Container]\nImage = \"alpine\"\n"
            ),
        }
        result = build_config_from_form(form)
        assert "version = 1" in result
        assert "[users.admin]" in result
        assert "ssh-ed25519 AAAA test@test" in result
        assert "[containers.container.myapp]" in result
        assert '[activation]\nrequired = ["myapp"]' in result

    def test_with_firewall(self):
        form = {
            "ssh_keys": "ssh-ed25519 AAAA test",
            "wan_tcp": "80\n443",
            "quadlet": (
                "[container.app]\nprivileged = false\n\n"
                "[container.app.Container]\nImage = \"x\"\n"
            ),
        }
        result = build_config_from_form(form)
        assert "[network.firewall.inbound.wan]" in result
        assert "tcp = [80, 443]" in result

    def test_with_os_upgrade(self):
        form = {
            "ssh_keys": "ssh-ed25519 AAAA test",
            "os_upgrade_server_url": "https://updates.example.com",
            "quadlet": (
                "[container.app]\nprivileged = false\n\n"
                "[container.app.Container]\nImage = \"x\"\n"
            ),
        }
        result = build_config_from_form(form)
        assert "[os_upgrade]" in result
        assert "https://updates.example.com" in result

    def test_quadlet_prefix_normalization(self):
        form = {
            "ssh_keys": "ssh-ed25519 AAAA test",
            "quadlet": (
                "[container.app]\nprivileged = false\n\n"
                "[container.app.Container]\nImage = \"x\"\n\n"
                "[network.mynet]\n\n[network.mynet.Network]\n"
            ),
        }
        result = build_config_from_form(form)
        assert "[containers.container.app]" in result
        assert "[containers.network.mynet]" in result

    def test_already_prefixed_not_doubled(self):
        form = {
            "ssh_keys": "ssh-ed25519 AAAA test",
            "quadlet": (
                "[containers.container.app]\nprivileged = false\n\n"
                "[containers.container.app.Container]\nImage = \"x\"\n"
            ),
        }
        result = build_config_from_form(form)
        # Should NOT become [containers.containers.container.app]
        assert "[containers.container.app]" in result
        assert "containers.containers" not in result
