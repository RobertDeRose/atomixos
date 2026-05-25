"""Tests for typed partial config updates."""

import tomllib

import pytest

from atomixos_provision.config import ProvisionError
from atomixos_provision.partial_config import (
    canonical_config_bytes,
    delete_resource,
    delete_user,
    patch_network,
    put_resource,
    put_user,
)

BASE_CONFIG = {
    "version": 1,
    "users": {"admin": {"isAdmin": True, "ssh_key": "ssh-ed25519 AAAA admin"}},
    "network": {"dns_servers": ["1.1.1.1"]},
    "activation": {"required": ["app"]},
    "containers": {
        "container": {"app": {"privileged": False, "Container": {"Image": "alpine"}}},
        "network": {"backend": {"Network": {"Subnet": "10.88.0.0/16"}}},
        "volume": {"data": {"Volume": {"Label": "data"}}},
    },
}


def test_canonical_config_bytes_round_trips_nested_tables():
    rendered = canonical_config_bytes(BASE_CONFIG)

    parsed = tomllib.loads(rendered.decode())
    assert parsed == BASE_CONFIG
    assert b"[containers.container.app.Container]\n" in rendered


def test_canonical_config_bytes_quotes_non_bare_keys():
    config = {
        "version": 1,
        "containers": {
            "container": {
                "web.api": {
                    "Container": {
                        "Image": "alpine",
                        "Environment": ["HTTP_PROXY=http://proxy.example"],
                    },
                    "X-Container": {"PodmanArgs": "--label app=web.api"},
                }
            }
        },
    }

    rendered = canonical_config_bytes(config)

    assert tomllib.loads(rendered.decode()) == config
    assert b'[containers.container."web.api".X-Container]\n' in rendered


def test_canonical_config_bytes_preserves_empty_tables():
    config = {
        "version": 1,
        "containers": {
            "network": {"empty-net": {"Network": {}}},
            "volume": {"empty-volume": {"Volume": {}}},
        },
    }

    rendered = canonical_config_bytes(config)

    assert tomllib.loads(rendered.decode()) == config
    assert b"[containers.network.empty-net.Network]\n" in rendered
    assert b"[containers.volume.empty-volume.Volume]\n" in rendered


def test_put_user_replaces_named_user():
    updated = put_user(
        BASE_CONFIG,
        "alice",
        {
            "isAdmin": False,
            "ssh_key": "ssh-ed25519 AAAA alice",
            "shell": "/run/current-system/sw/bin/zsh",
        },
    )

    assert updated["users"]["alice"]["isAdmin"] is False
    assert "alice" not in BASE_CONFIG["users"]


def test_put_user_rejects_extra_keys():
    with pytest.raises(ProvisionError, match="unsupported partial request keys"):
        put_user(BASE_CONFIG, "alice", {"isAdmin": False, "ssh_key": "k", "groups": ["wheel"]})


def test_delete_user_is_idempotent():
    updated = delete_user(BASE_CONFIG, "missing")

    assert updated == BASE_CONFIG


def test_patch_network_deep_merges_and_deletes_null_values():
    updated = patch_network(
        BASE_CONFIG,
        {
            "dns_servers": ["9.9.9.9"],
            "default_gateway": "192.0.2.1",
            "interfaces": {"eth0": {"mode": "dhcp"}},
        },
    )
    updated = patch_network(updated, {"default_gateway": None})

    assert updated["network"]["dns_servers"] == ["9.9.9.9"]
    assert updated["network"]["interfaces"]["eth0"]["mode"] == "dhcp"
    assert "default_gateway" not in updated["network"]


def test_put_and_delete_container_resource_tables():
    updated = put_resource(
        BASE_CONFIG,
        "container",
        "sidecar",
        {"privileged": False, "Container": {"Image": "docker.io/library/busybox:latest"}},
    )
    updated = delete_resource(updated, "network", "backend")

    assert updated["containers"]["container"]["sidecar"]["Container"]["Image"].endswith(
        "busybox:latest"
    )
    assert "backend" not in updated["containers"]["network"]


def test_put_resource_rejects_wrong_resource_shape():
    with pytest.raises(ProvisionError, match="unsupported partial request keys: Container"):
        put_resource(BASE_CONFIG, "network", "backend", {"Container": {"Image": "alpine"}})

    with pytest.raises(ProvisionError, match="container payload missing required key: privileged"):
        put_resource(BASE_CONFIG, "container", "sidecar", {"Container": {"Image": "alpine"}})
