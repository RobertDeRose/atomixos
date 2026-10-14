"""Tests for atomixos_provision.provision module."""

import json
import tarfile
import threading
import time
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
    validate_config_bytes,
    validate_config_from_path,
    write_imported_state,
)
from atomixos_provision.staging import (
    ensure_runtime_layout,
    publish_ready_marker,
    reserve_staged_job_slot,
    runtime_paths,
)

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


async def test_path_and_bytes_validation_report_the_same_schema_error(tmp_path):
    payload = BASE_PARTIAL_CONFIG.replace(
        "version = 1\n", "version = 1\nunexpected = true\n"
    ).encode()
    config_path = tmp_path / "config.toml"
    config_path.write_bytes(payload)

    with pytest.raises(ProvisionError) as path_error:
        validate_config_from_path(config_path, tmp_path / "active")
    with pytest.raises(ProvisionError) as bytes_error:
        await validate_config_bytes(payload, "config.toml", tmp_path / "active")

    assert str(path_error.value) == str(bytes_error.value)
    assert str(path_error.value) == "unsupported keys at config: unexpected"


def test_reconcile_bootstrap_wan_skips_fleet_transport(monkeypatch):
    """Verify that reconcile bootstrap wan skips fleet transport."""
    from atomixos_provision import provision

    monkeypatch.setenv("ATOMIXOS_BOOTSTRAP_TRANSPORT", "nixstasis")
    monkeypatch.setattr(
        provision.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("fleet transport must not reconcile WAN access"),
    )

    provision.reconcile_bootstrap_wan()


def test_schedule_bootstrap_rebind_skips_fleet_transport(monkeypatch):
    """Verify that schedule bootstrap rebind skips fleet transport."""
    from atomixos_provision import provision

    monkeypatch.setenv("ATOMIXOS_BOOTSTRAP_TRANSPORT", "nixstasis")
    monkeypatch.setattr(
        provision.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("fleet transport must not schedule socket rebind"),
    )

    provision.schedule_bootstrap_rebind({"lan_settings": {"gateway_ip": "10.44.0.1"}})


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
    """Verify that provisioning lock rejects writable runtime lock directory."""
    from atomixos_provision import provision

    lock_dir = tmp_path / "run-locks"
    lock_dir.mkdir()
    lock_dir.chmod(0o775)
    monkeypatch.setattr(provision, "PROVISION_LOCK_DIR", lock_dir)

    with (
        pytest.raises(ProvisionError, match="must not be group/world writable"),
        provisioning_lock(Path("/data/config")),
    ):
        pass


def test_provisioning_lock_rejects_non_root_runtime_lock_directory(monkeypatch, tmp_path):
    """Verify that provisioning lock rejects non root runtime lock directory."""
    from atomixos_provision import provision

    lock_dir = tmp_path / "run-locks"
    lock_dir.mkdir()
    monkeypatch.setattr(provision, "PROVISION_LOCK_DIR", lock_dir)
    monkeypatch.setattr(provision.os, "geteuid", lambda: 0)

    with (
        pytest.raises(ProvisionError, match="lock directory must be root-owned"),
        provisioning_lock(Path("/data/config")),
    ):
        pass


def test_locked_export_uses_runtime_lock_for_data_config(monkeypatch, tmp_path):
    """Exporting /data/config takes the runtime config lock and never runs recovery."""
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
        provision,
        "export_bundle_bytes",
        lambda _root: b"\x1f\x8bexported-bundle",
    )
    monkeypatch.setattr(
        provision,
        "recover_config_root",
        lambda _root: (_ for _ in ()).throw(AssertionError("export recovered root")),
    )

    assert locked_export_config_bytes(config_root) == b"\x1f\x8bexported-bundle"
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


async def test_stage_config_operation_does_not_recover_config_root(monkeypatch, tmp_path):
    """Verify that stage config operation does not recover config root."""
    from atomixos_provision import provision

    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text(BASE_PARTIAL_CONFIG)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        provision,
        "recover_config_root",
        lambda _root: (_ for _ in ()).throw(AssertionError("staging recovered root")),
    )

    await stage_config_operation(
        "job-1",
        {
            "op": "put_user",
            "name": "alice",
            "payload": {"isAdmin": False, "ssh_key": f"{VALID_ED25519_KEY} alice"},
        },
        config_root,
    )

    assert (runtime_root / "queue" / "job-1.ready").exists()


async def test_stage_config_operation_rejects_pending_promotion_without_recovery(
    monkeypatch, tmp_path
):
    from atomixos_provision import provision

    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text(BASE_PARTIAL_CONFIG)
    (tmp_path / "config.atomixos-promotion-pending").write_text("pending\n")
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        provision,
        "recover_config_root",
        lambda _root: (_ for _ in ()).throw(AssertionError("staging recovered root")),
    )

    with pytest.raises(ProvisionError, match="promotion recovery"):
        await stage_config_operation(
            "job-1",
            {
                "op": "put_user",
                "name": "alice",
                "payload": {"isAdmin": False, "ssh_key": f"{VALID_ED25519_KEY} alice"},
            },
            config_root,
        )

    assert not (runtime_root / "queue" / "job-1.ready").exists()


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


async def test_apply_config_operation_staged_path_waits_after_queueing(monkeypatch, tmp_path):
    """Verify that apply config operation staged path waits after queueing."""
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
    monkeypatch.setattr(
        provision,
        "_reserve_staged_job_or_raise",
        lambda _paths, _job_id: calls.append("reserve"),
    )

    result = await apply_config_operation(
        {"op": "put_user", "name": "alice", "payload": {"isAdmin": False, "ssh_key": "k"}},
        Path("/data/config"),
    )

    assert result == {"warnings": []}
    assert calls == ["reserve", "stage", "wait"]


async def test_apply_config_operation_direct_path_applies_candidate(monkeypatch, tmp_path):
    from atomixos_provision import provision

    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text(BASE_PARTIAL_CONFIG)
    monkeypatch.setenv("ATOMIXOS_ALLOW_UNSAFE_CONFIG_ROOT", "1")
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    monkeypatch.setattr(
        provision,
        "complete_reapply",
        lambda _root, _progress=None: (True, [], "skipped"),
    )
    monkeypatch.setattr(provision, "reconcile_bootstrap_wan", lambda: None)

    result = await apply_config_operation(
        {"op": "patch_network", "payload": {"dns_servers": ["9.9.9.9"]}},
        config_root,
    )

    assert result["reapply"] is True
    assert "9.9.9.9" in (config_root / "config.toml").read_text()


class _RecordingProgress:
    """Record progress stages reported by the staged-result wait."""

    def __init__(self):
        """Start with no recorded stages."""
        self.stages = []

    def set_stage(self, name, detail=None, **_fields):
        """Record a stage name and detail."""
        self.stages.append((name, detail))


def _wait_without_sleeping(monkeypatch, provision):
    """Reconcile liveness on every poll without real sleeps."""
    monkeypatch.setattr(provision, "STAGED_RESULT_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(provision.time, "sleep", lambda _seconds: None)


def _short_reservation_ttl(monkeypatch, *, heartbeat_seconds):
    """Expire reservations after 0.2s and set the local staging heartbeat."""
    from atomixos_provision import provision

    monkeypatch.setattr("atomixos_provision.staging.STAGED_RESERVATION_TTL_SECONDS", 0.2)
    monkeypatch.setattr(provision, "STAGED_RESERVATION_HEARTBEAT_SECONDS", heartbeat_seconds)


@pytest.mark.parametrize(("heartbeat_seconds", "survives"), [(0.05, True), (60, False)])
def test_local_staged_reservation_heartbeat_outlives_ttl(
    monkeypatch, tmp_path, heartbeat_seconds, survives
):
    """Verify that slow local staging keeps its reservation only via the heartbeat."""
    from atomixos_provision import provision

    paths = runtime_paths(tmp_path / "run")
    ensure_runtime_layout(paths, for_worker=True)
    _short_reservation_ttl(monkeypatch, heartbeat_seconds=heartbeat_seconds)

    with provision._local_staged_reservation(paths, "job-1"):
        time.sleep(0.5)
        if survives:
            assert publish_ready_marker(paths, "job-1").exists()
        else:
            with pytest.raises(ProvisionError, match="reservation is missing"):
                publish_ready_marker(paths, "job-1")


def test_local_staged_reservation_releases_and_stops_heartbeat_on_failure(monkeypatch, tmp_path):
    """Verify that a staging failure releases the slot and stops the heartbeat."""
    from atomixos_provision import provision

    paths = runtime_paths(tmp_path / "run")
    ensure_runtime_layout(paths, for_worker=True)
    _short_reservation_ttl(monkeypatch, heartbeat_seconds=0.05)

    with (
        pytest.raises(RuntimeError, match="render failed"),
        provision._local_staged_reservation(paths, "job-1"),
    ):
        assert (paths.queue / "job-1.reserve").exists()
        raise RuntimeError("render failed")

    assert not (paths.queue / "job-1.reserve").exists()
    assert not any(thread.name == "staged-reservation-job-1" for thread in threading.enumerate())


def test_wait_for_staged_result_keeps_claimed_job_nonterminal(monkeypatch, tmp_path):
    """Verify that wait for staged result keeps claimed job nonterminal."""
    from atomixos_provision import provision

    paths = runtime_paths(tmp_path / "run")
    ensure_runtime_layout(paths, for_worker=True)
    (paths.active / "job-1").mkdir()
    reads = {"count": 0}

    def read_result_after_two_intervals(_paths, _job_id):
        """Read result after two intervals."""
        reads["count"] += 1
        if reads["count"] < 3:
            return None
        return {"status": "succeeded", "result": {"warnings": []}}

    _wait_without_sleeping(monkeypatch, provision)
    monkeypatch.setattr(provision, "read_result", read_result_after_two_intervals)
    progress = _RecordingProgress()

    assert provision._wait_for_staged_result(paths, "job-1", progress) == {"warnings": []}
    assert reads["count"] == 3
    assert progress.stages == [("running", "privileged apply worker is running")]


def test_wait_for_staged_result_rereads_before_timeout_failure(monkeypatch, tmp_path):
    """Verify that a result published during timeout handling is returned."""
    from atomixos_provision import provision

    paths = runtime_paths(tmp_path / "run")
    ensure_runtime_layout(paths, for_worker=True)
    calls = {"count": 0}

    def fake_read_result(_paths, _job_id):
        calls["count"] += 1
        if calls["count"] < 2:
            return None
        return {"status": "succeeded", "result": {"warnings": []}}

    _wait_without_sleeping(monkeypatch, provision)
    monkeypatch.setattr(provision, "read_result", fake_read_result)

    assert provision._wait_for_staged_result(paths, "job-1") == {"warnings": []}


def test_wait_for_staged_result_abandons_queued_job_on_timeout(monkeypatch, tmp_path):
    """Verify that an unblocked queued job is abandoned and fails as timed out."""
    from atomixos_provision import provision

    paths = runtime_paths(tmp_path / "run")
    paths.queue.mkdir(parents=True)
    (paths.queue / "job-1").mkdir()
    (paths.queue / "job-1.ready").write_text(
        '{"job_id": "job-1", "sequence": 1}\n', encoding="utf-8"
    )
    _wait_without_sleeping(monkeypatch, provision)

    with pytest.raises(ProvisionError, match="timed out waiting"):
        provision._wait_for_staged_result(paths, "job-1")

    assert not (paths.queue / "job-1").exists()
    assert not (paths.queue / "job-1.ready").exists()


def test_wait_for_staged_result_fails_when_worker_removes_job_without_result(
    monkeypatch, tmp_path
):
    """Verify that a job removed without a result fails as unpublished."""
    from atomixos_provision import provision

    paths = runtime_paths(tmp_path / "run")
    paths.queue.mkdir(parents=True)
    _wait_without_sleeping(monkeypatch, provision)

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
    """Verify that write imported state uses private permissions and cleans quadlet."""
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
    assert (
        json.loads((config_root / "activation-policy.json").read_text())
        == parsed["activation_policy"]
    )


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


def test_import_config_from_path_reapply_migrates_legacy_config_without_marker(
    tmp_path, monkeypatch
):
    """Reapply an existing config even when it predates the first-config marker."""
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    activated_roots = []

    def complete_reapply(root, _progress=None):
        activated_roots.append(root)
        return True, [], "skipped"

    monkeypatch.setattr("atomixos_provision.provision.complete_reapply", complete_reapply)
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text(BASE_PARTIAL_CONFIG)
    source = tmp_path / "updated.toml"
    updated_config = BASE_PARTIAL_CONFIG.replace("alpine:latest", "busybox:latest")
    source.write_text(updated_config)
    assert not (config_root / ".first-config").exists()

    result = import_config_from_path(source, config_root)

    assert result["reapply"] is True
    assert result["rolled_back"] is False
    assert activated_roots == [config_root]
    assert (config_root / ".first-config").read_text() == "ok\n"
    assert (config_root / "config.toml").read_text() == updated_config
    assert (tmp_path / "config-rollback" / "config.toml").read_text() == BASE_PARTIAL_CONFIG


def test_durable_reapply_grants_writable_access_using_runtime_root(monkeypatch, tmp_path):
    """Keep absolute writable mounts enabled while reconciling a candidate root."""
    from atomixos_provision import provision

    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "config.toml").write_text("version = 1\n")
    candidate_root = tmp_path / "rendered-candidate"
    files_root = candidate_root / "files"
    files_root.mkdir(parents=True)
    (files_root / "state").write_text("state\n")
    (candidate_root / "config.toml").write_text("version = 1\n")
    parsed = {
        "containers": {
            "container": {
                "app": {
                    "Container": {
                        "Image": "alpine",
                        "Volume": f"{config_root}/files/state:/state:rw",
                    }
                }
            }
        }
    }
    grants = []
    monkeypatch.setattr(provision, "validate_config_root", lambda root, **_kwargs: root)
    monkeypatch.setattr(provision, "recover_config_root", lambda _root: None)
    monkeypatch.setattr(provision, "load_config", lambda _path: parsed)
    monkeypatch.setattr(provision, "_service_identity", lambda: (1000, 2000))
    monkeypatch.setattr(provision.os, "chown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        provision,
        "grant_managed_file_access",
        lambda path, *, writable=False: grants.append((path, writable)),
    )

    def complete_staged_apply(_root, _progress=None, *, before_commit=None):
        """Commit the staged apply without running activation."""
        if before_commit is not None:
            before_commit()
        return True, [], "skipped"

    monkeypatch.setattr(provision, "complete_reapply", complete_staged_apply)

    result = provision._promote_pre_rendered_candidate_sync(
        candidate_root,
        None,
        config_root,
        {"allow_reapply": True, "job_id": "job-1", "source_sha256": "a" * 64},
    )

    assert result["reapply"] is True
    assert grants == [(config_root.parent / "config-candidate" / "files", True)]


def test_import_config_reconciles_existing_config_without_first_marker(tmp_path, monkeypatch):
    """Verify that import reapplies an existing config and writes the first-config marker."""
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

    assert result["reapply"] is True
    assert (config_root / ".first-config").is_file()


def test_import_config_from_path_stages_data_config_outside_worker(monkeypatch, tmp_path):
    """Verify that import config from path stages data config outside worker."""
    from atomixos_provision import provision

    calls = []
    reservations = []
    config_path = tmp_path / "config.toml"
    config_path.write_text("version = 1\n")
    monkeypatch.setattr(provision, "validate_config_root", lambda _root: Path("/data/config"))
    monkeypatch.setattr(
        provision,
        "_stage_prepared_sync",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"queued": True},
    )
    monkeypatch.setattr(
        provision,
        "_reserve_staged_job_or_raise",
        lambda _paths, job_id: reservations.append(job_id),
    )

    result = import_config_from_path(config_path, Path("/data/config"))

    assert result == {"queued": True}
    assert calls
    assert reservations == [calls[0][0][0]]


def test_import_config_from_path_applies_data_config_in_worker(monkeypatch, tmp_path):
    from atomixos_provision import provision

    calls = []
    config_path = tmp_path / "config.toml"
    config_path.write_text("version = 1\n")
    monkeypatch.setenv("ATOMIXOS_PROVISION_WORKER_ACTIVE", "1")
    monkeypatch.setattr(provision, "validate_config_root", lambda _root: Path("/data/config"))
    monkeypatch.setattr(provision, "PROVISION_LOCK_DIR", tmp_path / "locks")
    monkeypatch.setattr(
        provision,
        "_stage_prepared_sync",
        lambda *args, **kwargs: pytest.fail("worker path must not stage"),
    )
    monkeypatch.setattr(
        provision,
        "_provision_prepared_sync",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"applied": True},
    )

    result = import_config_from_path(config_path, Path("/data/config"))

    assert result == {"applied": True}
    assert calls


async def test_apply_config_transform_preserves_bundle_files(tmp_path, monkeypatch):
    """Verify that apply config transform preserves bundle files."""
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
    monkeypatch.setattr(
        "atomixos_provision.bundle.grp.getgrnam",
        lambda _name: type("Gr", (), {"gr_gid": 2000})(),
    )
    monkeypatch.setattr("atomixos_provision.bundle.os.chown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("atomixos_provision.bundle.os.fchown", lambda *_args: None)

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


async def test_staged_partial_apply_preserves_bundle_files(tmp_path, monkeypatch):
    """Verify that staged partial apply preserves bundle files."""
    from atomixos_provision import provision

    def complete_staged_apply(root, _progress=None, *, before_commit=None):
        """Handle complete staged apply."""
        if before_commit is not None:
            before_commit()
        return True, [], "skipped"

    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("ATOMIXOS_ALLOW_UNSAFE_CONFIG_ROOT", "1")
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    monkeypatch.setattr(
        "atomixos_provision.provision.complete_reapply",
        complete_staged_apply,
    )
    monkeypatch.setattr("atomixos_provision.provision.reconcile_bootstrap_wan", lambda: None)
    monkeypatch.setattr("atomixos_provision.bundle.APP_RUNTIME_USER", "nobody")
    monkeypatch.setattr(
        "atomixos_provision.bundle.grp.getgrnam",
        lambda _name: type("Gr", (), {"gr_gid": 2000})(),
    )
    monkeypatch.setattr("atomixos_provision.bundle.os.chown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("atomixos_provision.bundle.os.fchown", lambda *_args: None)
    monkeypatch.setattr("atomixos_provision.provision.os.chown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        provision,
        "validate_config_root",
        lambda root, **_kwargs: root.resolve(strict=False),
    )

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
    await stage_config_operation(
        "job-1",
        {"op": "patch_network", "payload": {"dns_servers": ["9.9.9.9"]}},
        config_root,
    )
    result = provision.apply_staged_job(config_root, tmp_path / "run")

    assert result is not None
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


def test_retry_after_failed_initial_import_keeps_managed_users(tmp_path, monkeypatch):
    """A failed first apply's accounts stay managed, so a retry can update them."""
    monkeypatch.setenv("ATOMIXOS_BOOTSTRAP_ACTIVATION", "/tmp/fake-activation")
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    seen_managed = []

    def activation(succeed):
        def complete_reapply(root, _progress=None):
            # apply-users records what it manages before health checks run.
            seen_managed.append(
                sorted(json.loads((root / "managed-users.json").read_text()))
                if (root / "managed-users.json").exists()
                else []
            )
            (root / "managed-users.json").write_text('["admin"]\n')
            return (True, [], False) if succeed else (False, ["app.service"], False)

        return complete_reapply

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

    monkeypatch.setattr("atomixos_provision.provision.complete_reapply", activation(False))
    with pytest.raises(ProvisionError) as exc_info:
        import_config_from_path(config_path, config_root)
    assert exc_info.value.rollback_status == "discarded"
    assert sorted(path.name for path in config_root.iterdir()) == ["managed-users.json"]

    monkeypatch.setattr("atomixos_provision.provision.complete_reapply", activation(True))
    result = import_config_from_path(config_path, config_root)

    assert result["reapply"] is False
    assert seen_managed == [[], ["admin"]]
    assert (config_root / "config.toml").exists()
    assert json.loads((config_root / "managed-users.json").read_text()) == ["admin"]


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


def test_write_imported_state_grants_bundle_files_read_only_service_access(
    tmp_path, monkeypatch, managed_acl_calls
):
    """Install read-only bundle files as root-owned with appsvc ACL read access."""
    from atomixos_provision import provision

    config_path = tmp_path / "config.toml"
    config_path.write_text("version = 1\n")
    files_path = tmp_path / "source-files"
    files_path.mkdir()
    (files_path / "app.txt").write_text("app\n")
    config_root = tmp_path / "config"
    calls = []
    descriptor_calls = []
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
        "atomixos_provision.bundle.grp.getgrnam",
        lambda _name: type("Gr", (), {"gr_gid": 2000})(),
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
    monkeypatch.setattr(
        "atomixos_provision.bundle.os.fchown",
        lambda fd, uid, gid: descriptor_calls.append((fd, uid, gid)),
    )

    write_imported_state(parsed, config_path, files_path, config_root)

    assert descriptor_calls
    assert all((uid, gid) == (0, 2000) for _fd, uid, gid in descriptor_calls)
    # Install and the following service-access reconciliation each apply the ACL.
    assert sorted(perm for _uid, perm, _path in managed_acl_calls) == [0o4, 0o4, 0o5, 0o5]
    assert all(uid == 1000 for uid, _perm, _path in managed_acl_calls)
    assert (config_root / "files").stat().st_mode & 0o777 == 0o550
    assert (config_root / "files" / "app.txt").stat().st_mode & 0o777 == 0o440


def test_managed_file_writability_uses_runtime_config_root(tmp_path, monkeypatch):
    """Resolve absolute managed-file mounts against the supplied runtime root."""
    from atomixos_provision import provision

    config_root = tmp_path / "runtime-config"
    config_root.mkdir()
    (config_root / "config.toml").write_text("version = 1\n")
    parsed = {
        "containers": {
            "container": {
                "app": {
                    "Container": {
                        "Image": "alpine",
                        "Volume": f"{config_root}/files/state:/state:rw",
                    }
                }
            }
        }
    }
    monkeypatch.setattr(provision, "load_config", lambda _path: parsed)

    assert provision._managed_files_are_writable(config_root)


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
