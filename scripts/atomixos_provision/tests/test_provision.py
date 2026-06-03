"""Tests for atomixos_provision.provision module."""

import json
import tarfile
from pathlib import Path

import pytest

from atomixos_provision.config import ProvisionError
from atomixos_provision.provision import (
    apply_config_operation,
    apply_config_transform,
    import_config_from_path,
    locked_export_config_bytes,
    provisioning_lock,
    stage_config_operation,
    write_imported_state,
)
from atomixos_provision.staging import reserve_staged_job_slot, runtime_paths

VALID_ED25519_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAw"
)

BASE_PARTIAL_CONFIG = f"""\
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


def test_provisioning_lock_uses_runtime_lock_for_data_config(monkeypatch, tmp_path):
    from atomixos_provision import provision

    lock_dir = tmp_path / "run-locks"
    monkeypatch.setattr(provision, "PROVISION_LOCK_DIR", lock_dir)
    monkeypatch.setattr(provision.os, "geteuid", lambda: 1000)

    with provisioning_lock(Path("/data/config")):
        lock_path = lock_dir / "config.lock"
        assert lock_path.exists()
        assert lock_path.stat().st_mode & 0o600 == 0o600
        assert not lock_dir.stat().st_mode & 0o020


def test_provisioning_lock_rejects_writable_runtime_lock_directory(monkeypatch, tmp_path):
    from atomixos_provision import provision

    lock_dir = tmp_path / "run-locks"
    lock_dir.mkdir()
    lock_dir.chmod(0o775)
    monkeypatch.setattr(provision, "PROVISION_LOCK_DIR", lock_dir)

    with pytest.raises(
        ProvisionError, match="must not be group/world writable"
    ), provisioning_lock(Path("/data/config")):
        pass


def test_provisioning_lock_rejects_non_root_runtime_lock_directory(
    monkeypatch, tmp_path
):
    from atomixos_provision import provision

    lock_dir = tmp_path / "run-locks"
    lock_dir.mkdir()
    monkeypatch.setattr(provision, "PROVISION_LOCK_DIR", lock_dir)
    monkeypatch.setattr(provision.os, "geteuid", lambda: 0)

    with pytest.raises(
        ProvisionError, match="lock directory must be root-owned"
    ), provisioning_lock(Path("/data/config")):
        pass


def test_locked_export_uses_runtime_lock_for_data_config(monkeypatch, tmp_path):
    from atomixos_provision import provision

    data_root = tmp_path / "data"
    config_root = data_root / "config"
    config_root.mkdir(parents=True)
    (config_root / "config.toml").write_text("version = 1\n")
    lock_dir = tmp_path / "run-locks"
    monkeypatch.setattr(provision, "PROVISION_LOCK_DIR", lock_dir)
    monkeypatch.setattr(provision.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(
        provision,
        "validate_config_root",
        lambda root, **_kwargs: Path("/data/config") if root == config_root else root,
    )
    monkeypatch.setattr(
        "atomixos_provision.partial_config.export_config_bytes",
        lambda _root: (config_root / "config.toml").read_bytes(),
    )
    monkeypatch.setattr(
        provision,
        "recover_config_root",
        lambda _root: (_ for _ in ()).throw(AssertionError("export recovered root")),
    )

    assert locked_export_config_bytes(config_root) == b"version = 1\n"
    assert (lock_dir / "config.lock").exists()


async def test_stage_config_operation_queues_rendered_candidate(monkeypatch, tmp_path):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text(BASE_PARTIAL_CONFIG)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))

    await stage_config_operation(
        "job-1",
        {
            "op": "put_user",
            "name": "alice",
            "payload": {"isAdmin": False, "ssh_key": f"{VALID_ED25519_KEY} alice"},
        },
        config_root,
    )

    config_path = runtime_root / "queue" / "job-1" / "candidate" / "config.toml"
    manifest_path = runtime_root / "queue" / "job-1" / "manifest.json"
    assert (runtime_root / "queue" / "job-1.ready").exists()
    assert "[users.alice]" in config_path.read_text()
    assert json.loads(manifest_path.read_text())["operation"] == "partial-apply"


async def test_stage_config_operation_rejects_when_queue_not_empty(monkeypatch, tmp_path):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text(BASE_PARTIAL_CONFIG)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))

    assert reserve_staged_job_slot(runtime_paths(runtime_root), "other-job", 2) is True

    with pytest.raises(
        ProvisionError, match="partial config updates require an empty staged queue"
    ):
        await stage_config_operation(
            "job-1",
            {
                "op": "put_user",
                "name": "alice",
                "payload": {"isAdmin": False, "ssh_key": f"{VALID_ED25519_KEY} alice"},
            },
            config_root,
        )


async def test_apply_config_operation_staged_path_waits_after_queueing(
    monkeypatch, tmp_path
):
    from atomixos_provision import provision

    calls = []

    def fake_wait(_paths, job_id, _progress=None):
        assert job_id
        calls.append("wait")
        return {"warnings": []}

    monkeypatch.setattr(
        provision,
        "_stage_config_operation_sync",
        lambda *_args, **_kwargs: calls.append("stage"),
    )
    monkeypatch.setattr(provision, "_wait_for_staged_result", fake_wait)
    monkeypatch.setattr(provision, "staging_enabled", lambda: True)

    result = await apply_config_operation(
        {"op": "put_user", "name": "alice", "payload": {"isAdmin": False, "ssh_key": "k"}},
        Path("/data/config"),
    )

    assert result == {"warnings": []}
    assert calls == ["stage", "wait"]


def test_wait_for_staged_result_extends_while_worker_active(monkeypatch, tmp_path):
    from atomixos_provision import provision

    paths = runtime_paths(tmp_path / "run")
    (paths.active / "job-1").mkdir(parents=True)
    calls = {"count": 0}

    def fake_monotonic():
        calls["count"] += 1
        if calls["count"] == 1:
            return 0
        if calls["count"] == 2:
            return 2
        return 3

    def fake_read_result(_paths, _job_id):
        if calls["count"] >= 3:
            return {"status": "succeeded", "result": {"warnings": []}}
        return None

    monkeypatch.setattr(provision, "STAGED_RESULT_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(provision.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(provision.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(provision, "read_result", fake_read_result)

    assert provision._wait_for_staged_result(paths, "job-1") == {"warnings": []}


def test_wait_for_staged_result_rereads_before_timeout_failure(monkeypatch, tmp_path):
    from atomixos_provision import provision

    paths = runtime_paths(tmp_path / "run")
    calls = {"count": 0}

    def fake_read_result(_paths, _job_id):
        calls["count"] += 1
        if calls["count"] < 2:
            return None
        return {"status": "succeeded", "result": {"warnings": []}}

    times = iter([0, 0, 2])
    monkeypatch.setattr(provision, "STAGED_RESULT_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(provision.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(provision, "read_result", fake_read_result)

    assert provision._wait_for_staged_result(paths, "job-1") == {"warnings": []}


def test_wait_for_staged_result_abandons_queued_job_on_timeout(monkeypatch, tmp_path):
    from atomixos_provision import provision

    paths = runtime_paths(tmp_path / "run")
    paths.queue.mkdir(parents=True)
    (paths.queue / "job-1").mkdir()
    (paths.queue / "job-1.ready").write_text(
        '{"job_id": "job-1", "sequence": 1}\n', encoding="utf-8"
    )

    times = iter([0, 2, 2])
    monkeypatch.setattr(provision, "STAGED_RESULT_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(provision.time, "monotonic", lambda: next(times))

    with pytest.raises(ProvisionError, match="timed out waiting"):
        provision._wait_for_staged_result(paths, "job-1")

    assert not (paths.queue / "job-1").exists()
    assert not (paths.queue / "job-1.ready").exists()


def test_wait_for_staged_result_continues_if_worker_claims_timeout_job(
    monkeypatch, tmp_path
):
    from atomixos_provision import provision

    paths = runtime_paths(tmp_path / "run")
    (paths.active / "job-1").mkdir(parents=True)
    calls = {"count": 0}

    def fake_read_result(_paths, _job_id):
        calls["count"] += 1
        if calls["count"] < 3:
            return None
        return {"status": "succeeded", "result": {"warnings": []}}

    monkeypatch.setattr(provision, "STAGED_RESULT_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(provision.time, "monotonic", lambda: 2)
    monkeypatch.setattr(provision.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(provision, "read_result", fake_read_result)

    assert provision._wait_for_staged_result(paths, "job-1") == {"warnings": []}


def test_wait_for_staged_result_fails_when_worker_removes_job_without_result(
    monkeypatch, tmp_path
):
    from atomixos_provision import provision

    paths = runtime_paths(tmp_path / "run")
    paths.queue.mkdir(parents=True)

    times = iter([0, 2, 2])
    monkeypatch.setattr(provision, "STAGED_RESULT_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(provision.time, "monotonic", lambda: next(times))

    with pytest.raises(ProvisionError, match="did not publish a result"):
        provision._wait_for_staged_result(paths, "job-1")


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
        "host_network": {
            "dns_servers": ["1.1.1.1"],
            "dns_search_domains": ["lan.example"],
            "default_gateway": "192.0.2.1",
            "interfaces": {
                "eth0": {"mode": "dhcp"},
                "eth1": {"mode": "static", "address": "172.20.30.1/24"},
            },
        },
        "os_upgrade": {"server_url": "https://updates.example"},
        "required_units": ["app"],
        "activation_policy": {
            "required": ["app"],
            "timeout_seconds": 120,
            "settle_seconds": 5,
            "restart": ["app"],
            "allow_degraded": [],
            "strategy": "rollback",
        },
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
        "host-network.json",
        "os-upgrade.json",
        "health-required.json",
        "activation-policy.json",
        "quadlet-runtime.json",
    ]:
        assert (config_root / name).stat().st_mode & 0o777 == 0o600
    assert not stale_quadlet.exists()
    assert (config_root / "quadlet" / "app.container").exists()
    assert json.loads((config_root / "host-network.json").read_text()) == parsed["host_network"]
    assert json.loads((config_root / "activation-policy.json").read_text()) == parsed[
        "activation_policy"
    ]


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
    assert (config_root / ".first-config").read_text() == "ok\n"
    assert "busybox:latest" in (config_root / "config.toml").read_text()
    assert "alpine:latest" in (tmp_path / "config-rollback" / "config.toml").read_text()
    assert (config_root / "managed-users.json").read_text() == '["admin"]\n'


def test_import_config_reapply_requires_first_config_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    monkeypatch.setattr(
        "atomixos_provision.provision.complete_reapply",
        lambda _root, _progress=None: (True, [], False),
    )
    source = tmp_path / "config.toml"
    source.write_text(BASE_PARTIAL_CONFIG)
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text("version = 1\n")

    result = import_config_from_path(source, config_root)

    assert result["reapply"] is False
    assert (config_root / ".first-config").is_file()


def test_import_config_from_path_stages_data_config_outside_worker(monkeypatch, tmp_path):
    from atomixos_provision import provision

    calls = []
    config_path = tmp_path / "config.toml"
    config_path.write_text("version = 1\n")
    monkeypatch.setattr(provision, "validate_config_root", lambda _root: Path("/data/config"))
    monkeypatch.setattr(
        provision,
        "_stage_prepared_sync",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"queued": True},
    )

    result = import_config_from_path(config_path, Path("/data/config"))

    assert result == {"queued": True}
    assert calls


async def test_apply_config_transform_preserves_bundle_files(tmp_path, monkeypatch):
    monkeypatch.setenv("ATOMIXOS_ALLOW_UNSAFE_CONFIG_ROOT", "1")
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    monkeypatch.setattr(
        "atomixos_provision.provision.complete_reapply",
        lambda _root, _progress=None: (True, [], False),
    )
    monkeypatch.setattr("atomixos_provision.bundle.APP_RUNTIME_USER", "nobody")
    monkeypatch.setattr("atomixos_provision.bundle.os.chown", lambda *_args, **_kwargs: None)

    config_root = tmp_path / "config"
    bundle_root = tmp_path / "bundle-src"
    files_dir = bundle_root / "files" / "app"
    files_dir.mkdir(parents=True)
    (files_dir / "settings.json").write_text("{}\n")
    (bundle_root / "config.toml").write_text(
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
Volume = "${{FILES_DIR}}/app/settings.json:/settings.json:ro"
"""
    )
    bundle_path = tmp_path / "bundle.tar.gz"
    with tarfile.open(bundle_path, "w:gz") as archive:
        archive.add(bundle_root / "config.toml", arcname="config.toml")
        archive.add(bundle_root / "files", arcname="files")

    import_config_from_path(bundle_path, config_root)

    await apply_config_transform(
        lambda config: {**config, "network": {"dns_servers": ["9.9.9.9"]}},
        config_root,
    )

    assert (config_root / "files" / "app" / "settings.json").read_text() == "{}\n"
    unit_text = (config_root / "quadlet" / "app.container").read_text()
    assert f"Volume={config_root}/files/app/settings.json:/settings.json:ro" in unit_text


async def test_apply_config_transform_rejects_data_config_outside_worker(monkeypatch):
    monkeypatch.setattr(
        "atomixos_provision.provision.validate_config_root", lambda _root: Path("/data/config")
    )

    with pytest.raises(ProvisionError, match="must use staged operations"):
        await apply_config_transform(lambda config: config, Path("/data/config"))


def test_reapply_renders_network_settings_and_rolls_back_on_activation_failure(
    tmp_path, monkeypatch
):
    from atomixos_provision.activation import restore_rollback

    monkeypatch.setenv("ATOMIXOS_BOOTSTRAP_ACTIVATION", "/tmp/fake-activation")
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )

    def complete_reapply_with_network_failure(root, _progress=None):
        if not hasattr(complete_reapply_with_network_failure, "called"):
            complete_reapply_with_network_failure.called = True
            return True, [], ""
        assert restore_rollback(root)
        return False, ["lan-gateway-apply.service"], "completed"

    monkeypatch.setattr(
        "atomixos_provision.provision.complete_reapply",
        complete_reapply_with_network_failure,
    )
    first = tmp_path / "first.toml"
    first.write_text(
        f"""\
version = 1

[users.admin]
isAdmin = true
ssh_key = "{VALID_ED25519_KEY} admin@example"

[network]
dns_servers = ["1.1.1.1"]

[network.interfaces.eth1]
mode = "static"
address = "172.20.30.1/24"

[activation]
required = ["app"]

[containers.container.app]
privileged = false

[containers.container.app.Container]
Image = "docker.io/library/alpine:latest"
"""
    )
    second = tmp_path / "second.toml"
    second.write_text(first.read_text().replace("1.1.1.1", "9.9.9.9"))
    config_root = tmp_path / "config"

    import_config_from_path(first, config_root)

    with pytest.raises(ProvisionError, match="activation failed"):
        import_config_from_path(second, config_root)

    host_network = json.loads((config_root / "host-network.json").read_text())
    assert host_network["dns_servers"] == ["1.1.1.1"]


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


def test_write_imported_state_grants_service_read_access_when_root(tmp_path, monkeypatch):
    from atomixos_provision import provision

    config_path = tmp_path / "config.toml"
    config_path.write_text("version = 1\n")
    config_root = tmp_path / "config"
    calls = []
    parsed = {
        "ssh_keys": ["ssh-ed25519 AAAA admin@example"],
        "users": {"admin": {"isAdmin": True, "ssh_key": "ssh-ed25519 AAAA admin@example"}},
        "firewall_inbound": {},
        "lan_settings": {},
        "required_units": [],
        "containers": {},
    }

    monkeypatch.setattr(provision.os, "geteuid", lambda: 0)
    monkeypatch.setattr(provision, "_service_identity", lambda: (1000, 1000))
    monkeypatch.setattr(
        "atomixos_provision.bundle.pwd.getpwnam",
        lambda _name: type("Pw", (), {"pw_uid": 1000, "pw_gid": 1000})(),
    )
    monkeypatch.setattr(
        provision.os,
        "chown",
        lambda path, uid, gid, **_kwargs: calls.append((path, uid, gid)),
    )

    write_imported_state(parsed, config_path, None, config_root)

    assert (config_root, -1, 1000) in calls
    assert (config_root / "config.toml").stat().st_mode & 0o040


def test_write_imported_state_does_not_grant_service_group_to_bundle_files(
    tmp_path, monkeypatch
):
    from atomixos_provision import provision

    config_path = tmp_path / "config.toml"
    config_path.write_text("version = 1\n")
    files_path = tmp_path / "source-files"
    files_path.mkdir()
    (files_path / "app.txt").write_text("app\n")
    config_root = tmp_path / "config"
    calls = []
    parsed = {
        "ssh_keys": ["ssh-ed25519 AAAA admin@example"],
        "users": {"admin": {"isAdmin": True, "ssh_key": "ssh-ed25519 AAAA admin@example"}},
        "firewall_inbound": {},
        "lan_settings": {},
        "required_units": [],
        "containers": {},
    }

    monkeypatch.setattr(provision.os, "geteuid", lambda: 0)
    monkeypatch.setattr(provision, "_service_identity", lambda: (1000, 1000))
    monkeypatch.setattr(
        "atomixos_provision.bundle.pwd.getpwnam",
        lambda _name: type("Pw", (), {"pw_uid": 1000, "pw_gid": 1000})(),
    )
    monkeypatch.setattr(
        provision.os,
        "chown",
        lambda path, uid, gid, **_kwargs: calls.append((path, uid, gid)),
    )
    monkeypatch.setattr(
        "atomixos_provision.bundle.os.chown",
        lambda path, uid, gid, **_kwargs: calls.append((path, uid, gid)),
    )

    write_imported_state(parsed, config_path, files_path, config_root)

    assert (config_root / "files", -1, 1000) not in calls
    assert (config_root / "files" / "app.txt", -1, 1000) not in calls


def test_direct_initial_import_grants_service_read_access(tmp_path, monkeypatch):
    from atomixos_provision import provision

    config_path = tmp_path / "config.toml"
    config_path.write_text(BASE_PARTIAL_CONFIG)
    config_root = tmp_path / "config"
    calls = []

    monkeypatch.setattr(provision, "validate_config_root", lambda root, **_kwargs: root)
    monkeypatch.setattr(provision.os, "geteuid", lambda: 0)
    monkeypatch.setattr(provision, "_service_identity", lambda: (1000, 1000))
    monkeypatch.setattr(
        provision.os,
        "chown",
        lambda path, uid, gid, **_kwargs: calls.append((path, uid, gid)),
    )

    result = import_config_from_path(config_path, config_root)

    assert result["reapply"] is False
    assert (config_root.parent / "config-candidate", -1, 1000) in calls
    assert (config_root / "config.toml").stat().st_mode & 0o040
