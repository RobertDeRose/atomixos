"""Tests for atomixos_provision.provision module."""

import json

import pytest

from atomixos_provision.config import ProvisionError
from atomixos_provision.provision import (
    import_config_from_path,
    provisioning_lock,
    write_imported_state,
)

VALID_ED25519_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAw"
)


class ProgressRecorder:
    def __init__(self):
        self.stages = []

    def set_stage(self, name, detail=None, **fields):
        self.stages.append((name, detail, fields))


def test_provisioning_lock_blocks_nested_exclusive_lock(tmp_path):
    config_root = tmp_path / "config"

    with provisioning_lock(config_root), (tmp_path / ".config.lock").open("r+") as lock_file:
        import fcntl

        with pytest.raises(BlockingIOError):
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_write_imported_state_writes_apply_users_inputs(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("version = 1\n")
    config_root = tmp_path / "config"
    parsed = {
        "ssh_keys": ["ssh-ed25519 AAAA admin@example"],
        "users": {
            "admin": {"isAdmin": True, "ssh_key": "ssh-ed25519 AAAA admin@example"},
            "svc": {"isAdmin": False, "ssh_key": ""},
        },
        "firewall_inbound": {},
        "lan_settings": {},
        "required_units": [],
        "containers": {},
    }

    write_imported_state(parsed, config_path, None, config_root)

    assert (config_root / "users.json").exists()
    assert (config_root / "users.json").stat().st_mode & 0o777 == 0o600
    assert (config_root / "admin-signers").read_text() == "ssh-ed25519 AAAA admin@example\n"
    assert (config_root / "admin-signers").stat().st_mode & 0o777 == 0o600
    assert (
        config_root / "ssh-authorized-keys" / "admin"
    ).read_text() == "ssh-ed25519 AAAA admin@example\n"
    assert (config_root / "ssh-authorized-keys" / "admin").stat().st_mode & 0o777 == 0o600
    assert not (config_root / "ssh-authorized-keys" / "svc").exists()


def test_write_imported_state_uses_private_permissions_and_cleans_quadlet(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("version = 1\n")
    config_root = tmp_path / "config"
    stale_quadlet = config_root / "quadlet" / "stale.container"
    stale_quadlet.parent.mkdir(parents=True)
    stale_quadlet.write_text("[Container]\nImage=old\n")
    parsed = {
        "ssh_keys": ["ssh-ed25519 AAAA admin@example"],
        "users": {
            "admin": {"isAdmin": True, "ssh_key": "ssh-ed25519 AAAA admin@example"},
        },
        "firewall_inbound": {"wan": {"tcp": [443]}},
        "lan_settings": {"gateway_ip": "172.20.30.1"},
        "os_upgrade": {"server_url": "https://updates.example"},
        "required_units": ["app"],
        "containers": {
            "container": {
                "app": {
                    "privileged": False,
                    "Container": {"Image": "docker.io/library/alpine:latest"},
                },
            },
        },
    }

    write_imported_state(parsed, config_path, None, config_root)

    for name in [
        "config.toml",
        "firewall-inbound.json",
        "lan-settings.json",
        "os-upgrade.json",
        "health-required.json",
        "quadlet-runtime.json",
    ]:
        assert (config_root / name).stat().st_mode & 0o777 == 0o600
    assert not stale_quadlet.exists()
    assert (config_root / "quadlet" / "app.container").exists()


def test_write_imported_state_marks_build_rootless_when_consumed_by_rootless_container(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("version = 1\n")
    config_root = tmp_path / "config"
    parsed = {
        "ssh_keys": ["ssh-ed25519 AAAA admin@example"],
        "users": {
            "admin": {"isAdmin": True, "ssh_key": "ssh-ed25519 AAAA admin@example"},
        },
        "firewall_inbound": {},
        "lan_settings": {},
        "required_units": ["app"],
        "containers": {
            "container": {
                "app": {
                    "privileged": False,
                    "Container": {"Image": "localhost/custom:latest"},
                },
            },
            "build": {
                "custom": {
                    "Build": {"File": "Containerfile", "ImageTag": "localhost/custom:latest"},
                }
            },
        },
    }

    write_imported_state(parsed, config_path, None, config_root)

    runtime = json.loads((config_root / "quadlet-runtime.json").read_text())
    build = next(unit for unit in runtime["units"] if unit["filename"] == "custom.build")
    assert build["mode"] == "rootless"


def test_write_imported_state_rejects_quadlet_service_name_collision(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("version = 1\n")
    config_root = tmp_path / "config"
    parsed = {
        "ssh_keys": ["ssh-ed25519 AAAA admin@example"],
        "users": {
            "admin": {"isAdmin": True, "ssh_key": "ssh-ed25519 AAAA admin@example"},
        },
        "firewall_inbound": {},
        "lan_settings": {},
        "required_units": ["api-volume"],
        "containers": {
            "container": {
                "api-volume": {
                    "privileged": True,
                    "Container": {"Image": "docker.io/library/alpine:latest"},
                },
            },
            "volume": {
                "api": {
                    "Volume": {"Driver": "local"},
                },
            },
        },
    }

    with pytest.raises(ProvisionError, match="service name collision"):
        write_imported_state(parsed, config_path, None, config_root)


def test_write_imported_state_renders_mixed_mode_build_twice(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("version = 1\n")
    config_root = tmp_path / "config"
    parsed = {
        "ssh_keys": ["ssh-ed25519 AAAA admin@example"],
        "users": {
            "admin": {"isAdmin": True, "ssh_key": "ssh-ed25519 AAAA admin@example"},
        },
        "firewall_inbound": {},
        "lan_settings": {},
        "required_units": ["rootful", "rootless"],
        "containers": {
            "container": {
                "rootful": {
                    "privileged": True,
                    "Container": {"Image": "localhost/shared:latest"},
                },
                "rootless": {
                    "privileged": False,
                    "Container": {"Image": "localhost/shared:latest"},
                },
            },
            "build": {
                "shared": {
                    "Build": {"File": "Containerfile", "ImageTag": "localhost/shared:latest"},
                }
            },
        },
    }

    write_imported_state(parsed, config_path, None, config_root)

    runtime = json.loads((config_root / "quadlet-runtime.json").read_text())
    build_modes = sorted(
        unit["mode"] for unit in runtime["units"] if unit["filename"] == "shared.build"
    )
    assert build_modes == ["rootful", "rootless"]


def test_write_imported_state_marks_volume_rootless_when_consumed_by_rootless_container(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("version = 1\n")
    config_root = tmp_path / "config"
    parsed = {
        "ssh_keys": ["ssh-ed25519 AAAA admin@example"],
        "users": {
            "admin": {"isAdmin": True, "ssh_key": "ssh-ed25519 AAAA admin@example"},
        },
        "firewall_inbound": {},
        "lan_settings": {},
        "required_units": ["app"],
        "containers": {
            "container": {
                "app": {
                    "privileged": False,
                    "Container": {
                        "Image": "docker.io/library/alpine:latest",
                        "Volume": "data:/data:rw",
                    },
                },
            },
            "volume": {"data": {"Volume": {"Driver": "local"}}},
        },
    }

    write_imported_state(parsed, config_path, None, config_root)

    runtime = json.loads((config_root / "quadlet-runtime.json").read_text())
    volume = next(unit for unit in runtime["units"] if unit["filename"] == "data.volume")
    assert volume["mode"] == "rootless"


def test_write_imported_state_renders_quadlet_paths_for_runtime_root(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("version = 1\n")
    candidate_root = tmp_path / "config-candidate"
    runtime_root = tmp_path / "config"
    parsed = {
        "ssh_keys": ["ssh-ed25519 AAAA admin@example"],
        "users": {
            "admin": {"isAdmin": True, "ssh_key": "ssh-ed25519 AAAA admin@example"},
        },
        "firewall_inbound": {},
        "lan_settings": {},
        "required_units": ["caddy"],
        "containers": {
            "container": {
                "caddy": {
                    "privileged": True,
                    "Container": {
                        "Image": "docker.io/library/caddy:latest",
                        "Volume": "${FILES_DIR}/caddy/ui:/srv:ro",
                    },
                },
            },
        },
    }

    write_imported_state(parsed, config_path, None, candidate_root, runtime_root)

    unit_text = (candidate_root / "quadlet" / "caddy.container").read_text()
    assert f"Volume={runtime_root}/files/caddy/ui:/srv:ro" in unit_text
    assert "config-candidate/files/caddy/ui" not in unit_text


def test_import_config_from_path_reapply_preserves_rollback_and_managed_state(
    tmp_path, monkeypatch
):
    schema = {
        "type": "object",
        "additionalProperties": True,
    }
    monkeypatch.setattr("atomixos_provision.config.load_config_schema", lambda: schema)
    monkeypatch.setattr(
        "atomixos_provision.provision.complete_reapply",
        lambda _root, _progress=None: (True, [], False),
    )

    first = tmp_path / "first.toml"
    first.write_text(
        f"""\
version = 1

[users.admin]
isAdmin = true
ssh_key = "{VALID_ED25519_KEY} admin@example"

[activation]
required = ["app"]

[containers.container.app]
privileged = false

[containers.container.app.Container]
Image = "docker.io/library/alpine:latest"
"""
    )
    second = tmp_path / "second.toml"
    second.write_text(first.read_text().replace("alpine:latest", "busybox:latest"))
    config_root = tmp_path / "config"

    first_result = import_config_from_path(first, config_root)
    (config_root / "managed-users.json").write_text('["admin"]\n')
    second_result = import_config_from_path(second, config_root)

    assert first_result["reapply"] is False
    assert second_result["reapply"] is True
    assert "busybox:latest" in (config_root / "config.toml").read_text()
    assert "alpine:latest" in (tmp_path / "config-rollback" / "config.toml").read_text()
    assert (config_root / "managed-users.json").read_text() == '["admin"]\n'


def test_initial_import_skips_activation_without_bootstrap_hook(tmp_path, monkeypatch):
    monkeypatch.delenv("ATOMIXOS_BOOTSTRAP_ACTIVATION", raising=False)
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    monkeypatch.setattr(
        "atomixos_provision.provision.complete_reapply",
        lambda _root, _progress=None: (_ for _ in ()).throw(AssertionError("activated")),
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""\
version = 1

[users.admin]
isAdmin = true
ssh_key = "{VALID_ED25519_KEY} admin@example"

[activation]
required = ["app"]

[containers.container.app]
privileged = false

[containers.container.app.Container]
Image = "docker.io/library/alpine:latest"
"""
    )

    result = import_config_from_path(config_path, tmp_path / "config")

    assert result["reapply"] is False
    assert not (tmp_path / "config.atomixos-promotion-pending").exists()


def test_initial_import_can_keep_promotion_pending(tmp_path, monkeypatch):
    monkeypatch.delenv("ATOMIXOS_BOOTSTRAP_ACTIVATION", raising=False)
    monkeypatch.setenv("ATOMIXOS_KEEP_INITIAL_PROMOTION_PENDING", "1")
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""\
version = 1

[users.admin]
isAdmin = true
ssh_key = "{VALID_ED25519_KEY} admin@example"

[activation]
required = ["app"]

[containers.container.app]
privileged = false

[containers.container.app.Container]
Image = "docker.io/library/alpine:latest"
"""
    )

    result = import_config_from_path(config_path, tmp_path / "config")

    assert result["reapply"] is False
    assert (tmp_path / "config.atomixos-promotion-pending").exists()


def test_initial_import_discards_config_when_activation_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("ATOMIXOS_BOOTSTRAP_ACTIVATION", "/tmp/fake-activation")
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    monkeypatch.setattr(
        "atomixos_provision.provision.complete_reapply",
        lambda _root, _progress=None: (False, ["app.service"], False),
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""\
version = 1

[users.admin]
isAdmin = true
ssh_key = "{VALID_ED25519_KEY} admin@example"

[activation]
required = ["app"]

[containers.container.app]
privileged = false

[containers.container.app.Container]
Image = "docker.io/library/alpine:latest"
"""
    )
    config_root = tmp_path / "config"

    with pytest.raises(ProvisionError) as exc_info:
        import_config_from_path(config_path, config_root)

    assert "activation failed" in str(exc_info.value)
    assert exc_info.value.rollback_status == "discarded"
    assert not config_root.exists()
    assert not (tmp_path / "config-candidate").exists()
    assert not (tmp_path / "config-rollback").exists()
