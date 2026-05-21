"""Tests for atomixos_provision.quadlet module."""

from pathlib import Path

import pytest

from atomixos_provision.config import ProvisionError
from atomixos_provision.quadlet import (
    format_scalar,
    normalize_directives,
    render_builds,
    render_containers,
    render_networks,
    render_section,
    render_volumes,
    rewrite_rootless_publish_port,
    substitute_tokens,
)


class TestFormatScalar:
    def test_bool_true(self):
        assert format_scalar(True) == "true"

    def test_bool_false(self):
        assert format_scalar(False) == "false"

    def test_int(self):
        assert format_scalar(42) == "42"

    def test_string(self):
        assert format_scalar("hello") == "hello"

    def test_unsupported(self):
        with pytest.raises(ProvisionError, match="unsupported scalar"):
            format_scalar([1, 2])


class TestSubstituteTokens:
    def test_config_dir(self):
        result = substitute_tokens("${CONFIG_DIR}/file.conf", Path("/data/config"))
        assert result == "/data/config/file.conf"

    def test_files_dir(self):
        result = substitute_tokens("${FILES_DIR}/cert.pem", Path("/data/config"))
        assert result == "/data/config/files/cert.pem"

    def test_no_tokens(self):
        result = substitute_tokens("/etc/foo", Path("/data/config"))
        assert result == "/etc/foo"


class TestNormalizeDirectives:
    def test_scalar_to_list(self):
        result = normalize_directives({"Image": "alpine"}, "t")
        assert result == {"Image": ["alpine"]}

    def test_list_stays(self):
        result = normalize_directives({"Volume": ["/a:/b", "/c:/d"]}, "t")
        assert result == {"Volume": ["/a:/b", "/c:/d"]}

    def test_nested_dict_rejected(self):
        with pytest.raises(ProvisionError, match="expected scalar"):
            normalize_directives({"Bad": {"nested": True}}, "t")

    def test_rejects_injectable_directive_name(self):
        with pytest.raises(ProvisionError, match="invalid directive name"):
            normalize_directives({"Image\nExecStartPre": "alpine"}, "t")

    def test_rejects_multiline_value(self):
        with pytest.raises(ProvisionError, match="invalid newline"):
            normalize_directives({"Image": "alpine\n[Service]"}, "t")

    def test_empty_list_skipped(self):
        result = normalize_directives({"Empty": []}, "t")
        assert result == {}


class TestRewriteRootlessPublishPort:
    def test_simple_host_port(self):
        # "8080:80" → "127.0.0.1:8080:80"
        result = rewrite_rootless_publish_port("8080:80", "app", [])
        assert result == "127.0.0.1:8080:80"

    def test_already_loopback(self):
        result = rewrite_rootless_publish_port("127.0.0.1:8080:80", "app", [])
        assert result == "127.0.0.1:8080:80"

    def test_non_loopback_rewritten(self):
        warnings: list[str] = []
        result = rewrite_rootless_publish_port("0.0.0.0:8080:80", "app", warnings)
        assert result == "127.0.0.1:8080:80"
        assert len(warnings) == 1

    def test_ipv6_loopback(self):
        result = rewrite_rootless_publish_port("[::1]:8080:80", "app", [])
        assert result == "127.0.0.1:8080:80"

    def test_bare_container_port_rejected(self):
        with pytest.raises(ProvisionError, match="explicit host port"):
            rewrite_rootless_publish_port("8080", "app", [])

    def test_two_part_host_container_port_rejected(self):
        with pytest.raises(ProvisionError, match="numeric host port"):
            rewrite_rootless_publish_port("localhost:8080", "app", [])


class TestRenderSection:
    def test_basic(self):
        lines = render_section("Container", {"Image": ["alpine"]}, Path("/data/config"))
        assert lines[0] == "[Container]"
        assert "Image=alpine" in lines


class TestRenderContainers:
    def test_minimal_privileged(self):
        table = {
            "myapp": {
                "privileged": True,
                "Container": {"Image": "alpine:latest"},
            }
        }
        rendered, runtime, _warnings = render_containers(table, Path("/data/config"))
        assert "myapp.container" in rendered
        assert "Network=host" in rendered["myapp.container"]
        assert runtime[0]["mode"] == "rootful"

    def test_minimal_rootless(self):
        table = {
            "myapp": {
                "privileged": False,
                "Container": {"Image": "alpine:latest"},
            }
        }
        rendered, runtime, _warnings = render_containers(table, Path("/data/config"))
        assert "Network=pasta" in rendered["myapp.container"]
        assert runtime[0]["mode"] == "rootless"

    def test_empty_table(self):
        with pytest.raises(ProvisionError, match="at least one container"):
            render_containers({}, Path("/data/config"))

    def test_missing_image(self):
        table = {"app": {"privileged": False, "Container": {}}}
        with pytest.raises(ProvisionError, match="Image must be a single string"):
            render_containers(table, Path("/data/config"))


class TestRenderNetworks:
    def test_basic(self):
        table = {"mynet": {"Network": {"Driver": "bridge"}}}
        rendered, runtime = render_networks(table, Path("/data/config"))
        assert "mynet.network" in rendered
        assert "Driver=bridge" in rendered["mynet.network"]
        assert runtime[0]["mode"] == "rootful"

    def test_empty(self):
        rendered, _runtime = render_networks({}, Path("/data/config"))
        assert rendered == {}


class TestRenderVolumes:
    def test_basic(self):
        table = {"data": {"Volume": {"Driver": "local"}}}
        rendered, runtime = render_volumes(table, Path("/data/config"))
        assert "data.volume" in rendered
        assert runtime[0]["service"] == "data-volume.service"

    def test_rootless_mode_override(self):
        table = {"data": {"Volume": {"Driver": "local"}}}
        _rendered, runtime = render_volumes(
            table, Path("/data/config"), {"data": {"rootless"}}
        )
        assert runtime[0]["mode"] == "rootless"


class TestRenderBuilds:
    def test_basic(self):
        table = {"custom": {"Build": {"File": "Containerfile"}}}
        rendered, _runtime = render_builds(table, Path("/data/config"))
        assert "custom.build" in rendered
        assert "File=Containerfile" in rendered["custom.build"]

    def test_rootless_mode_override(self):
        table = {"custom": {"Build": {"File": "Containerfile"}}}
        _rendered, runtime = render_builds(
            table, Path("/data/config"), {"custom": {"rootless"}}
        )
        assert runtime[0]["mode"] == "rootless"
