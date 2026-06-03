"""Tests for staged provisioning jobs."""

import hashlib
import json
import os

import pytest

from atomixos_provision.config import ProvisionError
from atomixos_provision.provision import (
    apply_staged_job,
    stage_config_bytes,
    stage_config_operation,
)
from atomixos_provision.staging import (
    ClaimedJob,
    abandon_queued_job,
    can_abandon_queued_job,
    claim_next_job,
    count_staged_jobs,
    ensure_runtime_layout,
    finalize_abandoned_active_jobs,
    has_staged_jobs,
    read_result,
    refresh_staged_job_slot,
    release_staged_job_slot,
    reserve_staged_job_slot,
    runtime_paths,
    staged_job_presence,
    try_abandon_queued_job,
    verify_staged_job,
    write_json_atomic,
)

VALID_ED25519_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAw"
)


def _valid_config(image: str = "docker.io/library/alpine:latest") -> bytes:
    return f"""\
version = 1

[users.admin]
isAdmin = true
ssh_key = "{VALID_ED25519_KEY} admin@example"

[activation]
required = ["app"]

[containers.container.app]
privileged = false

[containers.container.app.Container]
Image = "{image}"
""".encode()


def test_staged_job_reservations_count_toward_queue_bound(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    paths = runtime_paths(runtime_root)

    assert reserve_staged_job_slot(paths, "job-1", 1) is True
    assert reserve_staged_job_slot(paths, "job-2", 1) is False
    assert count_staged_jobs(paths) == 1

    release_staged_job_slot(paths, "job-1")
    assert count_staged_jobs(paths) == 0


def test_staged_job_presence_can_exclude_current_reservation(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    paths = runtime_paths(runtime_root)

    assert reserve_staged_job_slot(paths, "job-1", 2) is True
    assert has_staged_jobs(paths) is True
    assert has_staged_jobs(paths, exclude_job_id="job-1") is False


def test_staged_job_count_treats_unreadable_active_dir_as_busy(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    paths = runtime_paths(runtime_root)
    ensure_runtime_layout(paths, for_worker=True)

    original_iterdir = type(paths.active).iterdir

    def deny_active_iterdir(path):
        if path == paths.active:
            raise PermissionError("permission denied")
        return original_iterdir(path)

    monkeypatch.setattr(type(paths.active), "iterdir", deny_active_iterdir)

    assert count_staged_jobs(paths) == 1
    assert has_staged_jobs(paths) is True


def test_refresh_staged_job_reservation_prevents_stale_cleanup(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr("atomixos_provision.staging.STAGED_RESERVATION_TTL_SECONDS", 60)
    paths = runtime_paths(runtime_root)

    assert reserve_staged_job_slot(paths, "job-1", 1) is True
    stale = 1
    os.utime(runtime_root / "queue" / "job-1.reserve", (stale, stale))
    refresh_staged_job_slot(paths, "job-1")

    assert count_staged_jobs(paths) == 1


def test_published_staged_jobs_replace_capacity_reservations(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    paths = runtime_paths(runtime_root)

    assert reserve_staged_job_slot(paths, "job-1", 1) is True
    stage_config_bytes(
        "job-1",
        _valid_config(),
        "config.toml",
        config_root,
    )

    assert not (runtime_root / "queue" / "job-1.reserve").exists()
    assert count_staged_jobs(paths) == 1
    assert reserve_staged_job_slot(paths, "job-2", 1) is False


def test_reserved_sequence_controls_fifo_ready_order(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    paths = runtime_paths(runtime_root)

    assert reserve_staged_job_slot(paths, "job-1", 2) is True
    assert reserve_staged_job_slot(paths, "job-2", 2) is True
    stage_config_bytes(
        "job-2",
        _valid_config("docker.io/library/busybox:latest"),
        "config.toml",
        tmp_path / "config",
    )
    stage_config_bytes("job-1", _valid_config(), "config.toml", tmp_path / "config")

    first = claim_next_job(paths)
    assert first is not None
    assert first.job_id == "job-1"


def _force_staging(monkeypatch) -> None:
    monkeypatch.delenv("ATOMIXOS_PROVISION_WORKER_ACTIVE", raising=False)


def test_stage_config_bytes_writes_manifest_and_ready_marker(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )

    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)

    manifest_path = runtime_root / "queue" / "job-1" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert (runtime_root / "queue" / "job-1.ready").exists()
    assert manifest["job_id"] == "job-1"
    assert manifest["operation"] == "initial-apply"
    assert manifest["candidate"]
    assert not (tmp_path / "config-candidate").exists()


def test_stage_config_bytes_stages_data_config_even_when_data_is_writable(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    data_root = tmp_path / "data"
    config_root = data_root / "config"
    data_root.mkdir()
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.provision.validate_config_root",
        lambda root, **_kwargs: config_root if root == config_root else root,
    )
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )

    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)

    assert (runtime_root / "queue" / "job-1.ready").exists()
    assert not (config_root / "config.toml").exists()


def test_claim_next_job_uses_ready_marker_sequence_order(tmp_path):
    paths = runtime_paths(tmp_path / "run")
    ensure_runtime_layout(paths, for_worker=True)
    for job_id, sequence in [("z-job", 2), ("a-job", 1)]:
        (paths.queue / job_id).mkdir()
        (paths.queue / f"{job_id}.ready").write_text(
            json.dumps({"job_id": job_id, "sequence": sequence}) + "\n",
            encoding="utf-8",
        )

    claimed = claim_next_job(paths)

    assert claimed is not None
    assert claimed.job_id == "a-job"


def test_claim_next_job_does_not_reclaim_active_job(tmp_path):
    paths = runtime_paths(tmp_path / "run")
    ensure_runtime_layout(paths, for_worker=True)
    (paths.active / "active-job").mkdir()
    (paths.queue / "queued-job").mkdir()
    (paths.queue / "queued-job.ready").write_text(
        json.dumps({"job_id": "queued-job", "sequence": 1}) + "\n",
        encoding="utf-8",
    )

    assert claim_next_job(paths) is None
    assert (paths.active / "active-job").exists()
    assert (paths.queue / "queued-job").exists()


def test_claim_next_job_rejects_ready_marker_without_sequence(tmp_path):
    paths = runtime_paths(tmp_path / "run")
    ensure_runtime_layout(paths, for_worker=True)
    (paths.queue / "job-1").mkdir()
    (paths.queue / "job-1.ready").write_text(
        json.dumps({"job_id": "job-1", "created_at": 1.0}) + "\n",
        encoding="utf-8",
    )

    assert claim_next_job(paths) is None
    assert not (paths.queue / "job-1.ready").exists()


def test_claim_next_job_skips_symlinked_queued_job(tmp_path):
    paths = runtime_paths(tmp_path / "run")
    ensure_runtime_layout(paths, for_worker=True)
    target = tmp_path / "target"
    target.mkdir()
    (paths.queue / "job-1").symlink_to(target)
    (paths.queue / "job-1.ready").write_text(
        json.dumps({"job_id": "job-1", "sequence": 1}) + "\n",
        encoding="utf-8",
    )

    assert claim_next_job(paths) is None
    assert not (paths.queue / "job-1.ready").exists()
    assert (paths.queue / "job-1").is_symlink()


def test_read_json_rejects_symlink(tmp_path):
    from atomixos_provision.staging import read_json

    target = tmp_path / "target.json"
    target.write_text("{}\n", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)

    with pytest.raises(ProvisionError, match="must not be a symlink"):
        read_json(link)


def test_read_json_rejects_large_control_file(tmp_path):
    from atomixos_provision.staging import read_json

    path = tmp_path / "large.json"
    path.write_bytes(b"{" + (b" " * (1024 * 1024 + 1)) + b"}")

    with pytest.raises(ProvisionError, match="too large"):
        read_json(path)


def test_claim_next_job_skips_malformed_ready_marker(tmp_path):
    paths = runtime_paths(tmp_path / "run")
    ensure_runtime_layout(paths, for_worker=True)
    for job_id, payload in [
        ("bad", {"job_id": "bad"}),
        ("good", {"job_id": "good", "sequence": 2}),
    ]:
        (paths.queue / job_id).mkdir()
        (paths.queue / f"{job_id}.ready").write_text(
            json.dumps(payload) + "\n",
            encoding="utf-8",
        )

    claimed = claim_next_job(paths)

    assert claimed is not None
    assert claimed.job_id == "good"
    assert not (paths.queue / "bad.ready").exists()


def test_try_abandon_queued_job_removes_unclaimed_job(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)
    paths = runtime_paths(runtime_root)

    assert can_abandon_queued_job(paths, "job-1") is True
    assert staged_job_presence(paths, "job-1") == "queued"
    assert try_abandon_queued_job(paths, "job-1") is True

    assert staged_job_presence(paths, "job-1") == "missing"
    assert not (runtime_root / "queue" / "job-1").exists()
    assert not (runtime_root / "queue" / "job-1.ready").exists()


def test_abandon_queued_job_removes_unclaimed_job(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)
    paths = runtime_paths(runtime_root)

    abandon_queued_job(paths, "job-1")

    assert not (runtime_root / "queue" / "job-1").exists()
    assert not (runtime_root / "queue" / "job-1.ready").exists()


def test_abandon_queued_job_rejects_claimed_job(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)
    paths = runtime_paths(runtime_root)
    claimed = claim_next_job(paths)
    assert claimed is not None

    assert can_abandon_queued_job(paths, "job-1") is False
    assert staged_job_presence(paths, "job-1") == "active"
    assert try_abandon_queued_job(paths, "job-1") is False
    with pytest.raises(ProvisionError, match="cannot abandon staged job"):
        abandon_queued_job(paths, "job-1")


def test_finalize_abandoned_active_jobs_marks_claimed_job_failed(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)
    paths = runtime_paths(runtime_root)
    claimed = claim_next_job(paths)
    assert claimed is not None

    assert finalize_abandoned_active_jobs(paths, "worker stopped") == 1

    assert not (runtime_root / "active" / "job-1").exists()
    result = read_result(paths, "job-1")
    assert result is not None
    assert result["status"] == "failed"
    assert result["error"] == "worker stopped"


def test_runtime_layout_keeps_results_read_only_for_service_group(tmp_path):
    paths = runtime_paths(tmp_path / "run")

    ensure_runtime_layout(paths, for_worker=True)

    assert paths.queue.stat().st_mode & 0o7777 == 0o2770
    assert paths.results.stat().st_mode & 0o7777 == 0o2750


def test_read_result_rejects_group_writable_results_directory(tmp_path):
    paths = runtime_paths(tmp_path / "run")
    ensure_runtime_layout(paths, for_worker=True)
    paths.results.chmod(0o2770)

    with pytest.raises(ProvisionError, match="results directory must not be group/world writable"):
        read_result(paths, "job-1")


def test_read_result_rejects_group_writable_result_file(tmp_path):
    paths = runtime_paths(tmp_path / "run")
    ensure_runtime_layout(paths)
    write_json_atomic(
        paths.results / "job-1.json",
        {"version": 1, "job_id": "job-1", "status": "succeeded", "result": {}},
        mode=0o660,
    )

    with pytest.raises(ProvisionError, match="result must not be group/world writable"):
        read_result(paths, "job-1")


def test_verify_staged_job_rejects_tampered_file(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)
    paths = runtime_paths(runtime_root)
    claimed = claim_next_job(paths)
    assert claimed is not None

    (claimed.path / "candidate" / "config.toml").write_text("version = 1\n")

    with pytest.raises(ProvisionError, match=r"staged file (hash|size) changed"):
        verify_staged_job(ClaimedJob("job-1", claimed.path), paths)


def test_apply_staged_job_promotes_candidate_and_writes_result(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.provision.validate_config_root", lambda root, **_: root
    )
    monkeypatch.setattr("atomixos_provision.provision.os.chown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    monkeypatch.setattr(
        "atomixos_provision.provision.complete_reapply",
        lambda _root, _progress=None: (True, [], "skipped"),
    )
    monkeypatch.setattr("atomixos_provision.provision.reconcile_bootstrap_wan", lambda: None)

    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)
    result = apply_staged_job(config_root, runtime_root)

    assert result is not None
    assert result["reapply"] is False
    assert (config_root / "config.toml").exists()
    assert (config_root / ".first-config").read_text() == "ok\n"
    assert not (runtime_root / "active" / "job-1").exists()
    result_file = json.loads((runtime_root / "results" / "job-1.json").read_text())
    assert result_file["status"] == "succeeded"


def test_apply_staged_job_verifies_active_source_before_snapshot_copy(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.provision.validate_config_root", lambda root, **_: root
    )
    monkeypatch.setattr("atomixos_provision.provision.os.chown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )

    from atomixos_provision import provision

    original_verify = provision.verify_staged_job

    def reject_active_source(job, _paths, **kwargs):
        if kwargs.get("require_active", True):
            raise ProvisionError("source verification failed")
        return original_verify(job, _paths, **kwargs)

    monkeypatch.setattr(provision, "verify_staged_job", reject_active_source)
    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)

    with pytest.raises(ProvisionError, match="source verification failed"):
        apply_staged_job(config_root, runtime_root)


def test_apply_staged_job_rerenders_derived_state_from_config(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.provision.validate_config_root", lambda root, **_: root
    )
    monkeypatch.setattr("atomixos_provision.provision.os.chown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    monkeypatch.setattr(
        "atomixos_provision.provision.complete_reapply",
        lambda _root, _progress=None: (True, [], "skipped"),
    )
    monkeypatch.setattr("atomixos_provision.provision.reconcile_bootstrap_wan", lambda: None)

    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)
    users_path = runtime_root / "queue" / "job-1" / "candidate" / "users.json"
    users_path.write_text('["attacker"]\n', encoding="utf-8")
    manifest_path = runtime_root / "queue" / "job-1" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest["candidate"]:
        if entry.get("path") == "users.json":
            entry["size"] = users_path.stat().st_size
            entry["sha256"] = hashlib.sha256(users_path.read_bytes()).hexdigest()
            break
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = apply_staged_job(config_root, runtime_root)

    assert result is not None
    assert "attacker" not in (config_root / "users.json").read_text()


def test_staged_snapshot_preserves_nested_directory_modes(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.provision.validate_config_root", lambda root, **_: root
    )
    monkeypatch.setattr("atomixos_provision.provision.os.chown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    monkeypatch.setattr(
        "atomixos_provision.provision.complete_reapply",
        lambda _root, _progress=None: (True, [], "skipped"),
    )
    monkeypatch.setattr("atomixos_provision.provision.reconcile_bootstrap_wan", lambda: None)

    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)

    result = apply_staged_job(config_root, runtime_root)

    assert result is not None
    assert (config_root / "quadlet").is_dir()


def test_staged_snapshot_reapplies_directory_modes_after_file_copy(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.provision.validate_config_root", lambda root, **_: root
    )
    monkeypatch.setattr("atomixos_provision.provision.os.chown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    monkeypatch.setattr(
        "atomixos_provision.provision.complete_reapply",
        lambda _root, _progress=None: (True, [], "skipped"),
    )
    monkeypatch.setattr("atomixos_provision.provision.reconcile_bootstrap_wan", lambda: None)

    from atomixos_provision import provision

    original_copy = provision._copy_staged_file_from_path

    def copy_then_clobber_parent(source, destination, expected_size=None):
        result = original_copy(source, destination, expected_size)
        if destination.parent.name == "quadlet":
            destination.parent.chmod(0o700)
        return result

    monkeypatch.setattr(provision, "_copy_staged_file_from_path", copy_then_clobber_parent)

    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)

    result = apply_staged_job(config_root, runtime_root)

    assert result is not None


def test_staged_snapshot_preserves_special_directory_mode_bits(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.provision.validate_config_root", lambda root, **_: root
    )
    monkeypatch.setattr("atomixos_provision.provision.os.chown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    monkeypatch.setattr(
        "atomixos_provision.provision.complete_reapply",
        lambda _root, _progress=None: (True, [], "skipped"),
    )
    monkeypatch.setattr("atomixos_provision.provision.reconcile_bootstrap_wan", lambda: None)

    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)
    quadlet_dir = runtime_root / "queue" / "job-1" / "candidate" / "quadlet"
    quadlet_dir.chmod(0o2755)
    manifest_path = runtime_root / "queue" / "job-1" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest["candidate"]:
        if entry.get("path") == "quadlet":
            entry["mode"] = 0o2755
            break
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = apply_staged_job(config_root, runtime_root)

    assert result is not None


def test_apply_staged_job_promotes_verified_snapshot_not_mutated_active_tree(
    tmp_path, monkeypatch
):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.provision.validate_config_root", lambda root, **_: root
    )
    monkeypatch.setattr("atomixos_provision.provision.os.chown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    monkeypatch.setattr(
        "atomixos_provision.provision.complete_reapply",
        lambda _root, _progress=None: (True, [], "skipped"),
    )
    monkeypatch.setattr("atomixos_provision.provision.reconcile_bootstrap_wan", lambda: None)

    from atomixos_provision import provision

    original_verify = provision.verify_staged_job

    def tamper_active_tree_after_snapshot(job, paths, **kwargs):
        if kwargs.get("require_active") is False:
            active_config = paths.active / job.job_id / "candidate" / "config.toml"
            if active_config.exists():
                active_config.write_text("version = 1\n", encoding="utf-8")
        return original_verify(job, paths, **kwargs)

    monkeypatch.setattr(provision, "verify_staged_job", tamper_active_tree_after_snapshot)

    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)

    result = apply_staged_job(config_root, runtime_root)

    assert result is not None
    assert 'Image = "docker.io/library/alpine:latest"' in (config_root / "config.toml").read_text()


@pytest.mark.asyncio
async def test_apply_staged_partial_renders_against_current_config(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.provision.validate_config_root", lambda root, **_: root
    )
    monkeypatch.setattr("atomixos_provision.provision.os.chown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    monkeypatch.setattr(
        "atomixos_provision.provision.complete_reapply",
        lambda _root, _progress=None: (True, [], "skipped"),
    )
    monkeypatch.setattr("atomixos_provision.provision.reconcile_bootstrap_wan", lambda: None)

    stage_config_bytes(
        "job-1", _valid_config("docker.io/library/nginx:latest"), "config.toml", config_root
    )
    first = apply_staged_job(config_root, runtime_root)
    assert first is not None
    await stage_config_operation(
        "job-2",
        {
            "op": "put_resource",
            "table": "container",
            "name": "app",
            "payload": {
                "privileged": False,
                "Container": {"Image": "docker.io/library/caddy:latest"},
            },
        },
        config_root,
    )

    second = apply_staged_job(config_root, runtime_root)

    assert second is not None
    assert 'Image = "docker.io/library/caddy:latest"' in (
        config_root / "config.toml"
    ).read_text()


@pytest.mark.asyncio
async def test_apply_staged_partial_rejects_tampered_candidate_config(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.provision.validate_config_root", lambda root, **_: root
    )
    monkeypatch.setattr("atomixos_provision.provision.os.chown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    monkeypatch.setattr(
        "atomixos_provision.provision.complete_reapply",
        lambda _root, _progress=None: (True, [], "skipped"),
    )
    monkeypatch.setattr("atomixos_provision.provision.reconcile_bootstrap_wan", lambda: None)

    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)
    apply_staged_job(config_root, runtime_root)
    await stage_config_operation(
        "job-2",
        {
            "op": "put_user",
            "name": "alice",
            "payload": {"isAdmin": False, "ssh_key": f"{VALID_ED25519_KEY} alice"},
        },
        config_root,
    )
    config_path = runtime_root / "queue" / "job-2" / "candidate" / "config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("alice", "admin"),
        encoding="utf-8",
    )

    with pytest.raises(ProvisionError, match="staged file hash changed"):
        apply_staged_job(config_root, runtime_root)


def test_apply_staged_job_rejects_tampering_without_data_mutation(tmp_path, monkeypatch):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.provision.validate_config_root", lambda root, **_: root
    )
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )
    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)
    candidate_config = runtime_root / "queue" / "job-1" / "candidate" / "config.toml"
    candidate_config.write_text("version = 1\n")

    with pytest.raises(ProvisionError, match=r"staged file (hash|size) changed"):
        apply_staged_job(config_root, runtime_root)

    assert not config_root.exists()
    result_file = json.loads((runtime_root / "results" / "job-1.json").read_text())
    assert result_file["status"] == "failed"
    assert "staged file" in result_file["error"]


def test_apply_staged_job_rejects_unexpected_top_level_before_snapshot(
    tmp_path, monkeypatch
):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    copied_paths = []
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.provision.validate_config_root", lambda root, **_: root
    )
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )

    from atomixos_provision import provision

    original_copy = provision._copy_staged_file_from_path


    def recording_copy(source, destination, expected_size=None):
        copied_paths.append(source.name)
        return original_copy(source, destination, expected_size)

    monkeypatch.setattr(provision, "_copy_staged_file_from_path", recording_copy)

    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)
    junk_path = runtime_root / "queue" / "job-1" / "unexpected.bin"
    junk_path.write_bytes(b"not in manifest")

    with pytest.raises(ProvisionError, match="unexpected top-level entries"):
        apply_staged_job(config_root, runtime_root)

    assert copied_paths == []
    assert not config_root.exists()


def test_apply_staged_job_rejects_size_race_without_snapshot_copy(
    tmp_path, monkeypatch
):
    runtime_root = tmp_path / "run"
    config_root = tmp_path / "config"
    copied_bytes = []
    _force_staging(monkeypatch)
    monkeypatch.setenv("ATOMIXOS_PROVISION_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(
        "atomixos_provision.provision.validate_config_root", lambda root, **_: root
    )
    monkeypatch.setattr(
        "atomixos_provision.config.load_config_schema",
        lambda: {"type": "object", "additionalProperties": True},
    )

    from atomixos_provision import provision

    original_copy_stream = provision._copy_staged_file_stream


    def recording_copy_stream(source_file, source, destination, expected_size):
        if source.name == "config.toml" and source.parent.name == "candidate":
            copied_bytes.append(source.stat().st_size)
        return original_copy_stream(source_file, source, destination, expected_size)

    monkeypatch.setattr(provision, "_copy_staged_file_stream", recording_copy_stream)

    stage_config_bytes("job-1", _valid_config(), "config.toml", config_root)
    config_path = runtime_root / "queue" / "job-1" / "candidate" / "config.toml"
    config_path.write_text(config_path.read_text() + "# size race\n", encoding="utf-8")
    with pytest.raises(ProvisionError, match="staged file size changed"):
        apply_staged_job(config_root, runtime_root)

    assert copied_bytes == []
    assert not config_root.exists()
