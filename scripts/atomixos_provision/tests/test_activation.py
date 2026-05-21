"""Tests for atomixos_provision.activation module."""

import json
import subprocess

from atomixos_provision.activation import (
    activate_services,
    atomic_promote,
    atomic_promote_initial,
    carry_forward_managed_state,
    check_required_services,
    cleanup_rollback,
    complete_reapply,
    discard_initial_config,
    read_managed_state,
    recover_config_root,
    report_runtime_deploy_start,
    report_runtime_services,
    restore_rollback,
    write_managed_state,
)


class ProgressRecorder:
    def __init__(self):
        self.stages = []

    def set_stage(self, name, detail=None, **fields):
        self.stages.append((name, detail, fields))


class TestRecoverConfigRoot:
    def test_no_recovery_needed(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        (config_root / "config.toml").write_text("version = 1")
        recover_config_root(config_root)
        assert (config_root / "config.toml").exists()

    def test_marker_with_rollback_restores_when_active_missing(self, tmp_path):
        config_root = tmp_path / "config"
        rollback = tmp_path / "config-rollback"
        rollback.mkdir()
        (rollback / "config.toml").write_text("old")
        marker = tmp_path / "config.atomixos-promotion-pending"
        marker.write_text("pending\n")
        recover_config_root(config_root)
        assert (config_root / "config.toml").read_text() == "old"
        assert not rollback.exists()
        assert not marker.exists()

    def test_marker_with_active_and_rollback_restores_rollback(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        (config_root / "config.toml").write_text("new")
        rollback = tmp_path / "config-rollback"
        rollback.mkdir()
        (rollback / "config.toml").write_text("old")
        marker = tmp_path / "config.atomixos-promotion-pending"
        marker.write_text("pending\n")

        recover_config_root(config_root)

        assert (config_root / "config.toml").read_text() == "old"
        assert not rollback.exists()
        assert not marker.exists()

    def test_marker_without_rollback(self, tmp_path):
        config_root = tmp_path / "config"
        marker = tmp_path / "config.atomixos-promotion-pending"
        marker.write_text("pending\n")
        recover_config_root(config_root)
        assert not marker.exists()

    def test_marker_without_rollback_preserves_active_config(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        (config_root / "config.toml").write_text("active")
        candidate = tmp_path / "config-candidate"
        candidate.mkdir()
        (candidate / "config.toml").write_text("stale")
        marker = tmp_path / "config.atomixos-promotion-pending"
        marker.write_text("pending\n")

        recover_config_root(config_root)

        assert (config_root / "config.toml").read_text() == "active"
        assert not candidate.exists()
        assert not marker.exists()

    def test_initial_candidate_discarded_when_active_missing(self, tmp_path):
        config_root = tmp_path / "config"
        candidate = tmp_path / "config-candidate"
        candidate.mkdir()
        (candidate / "config.toml").write_text("new")
        marker = tmp_path / "config.atomixos-promotion-pending"
        marker.write_text("pending\n")
        recover_config_root(config_root)
        assert not config_root.exists()
        assert not candidate.exists()
        assert not marker.exists()

    def test_unmarked_candidate_is_discarded_when_active_missing(self, tmp_path):
        config_root = tmp_path / "config"
        candidate = tmp_path / "config-candidate"
        candidate.mkdir()
        (candidate / "config.toml").write_text("partial")

        recover_config_root(config_root)

        assert not config_root.exists()
        assert not candidate.exists()

    def test_unmarked_candidate_is_discarded_when_active_exists(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        (config_root / "config.toml").write_text("active")
        candidate = tmp_path / "config-candidate"
        candidate.mkdir()
        (candidate / "config.toml").write_text("partial")

        recover_config_root(config_root)

        assert (config_root / "config.toml").read_text() == "active"
        assert not candidate.exists()


class TestAtomicPromote:
    def test_basic_promotion(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        (config_root / "config.toml").write_text("old")
        candidate = tmp_path / "config-candidate"
        candidate.mkdir()
        (candidate / "config.toml").write_text("new")

        atomic_promote(config_root, candidate)

        assert (config_root / "config.toml").read_text() == "new"
        rollback = tmp_path / "config-rollback"
        assert (rollback / "config.toml").read_text() == "old"
        assert (tmp_path / "config.atomixos-promotion-pending").exists()

    def test_initial_promotion_removes_stale_rollback(self, tmp_path):
        config_root = tmp_path / "config"
        candidate = tmp_path / "config-candidate"
        candidate.mkdir()
        (candidate / "config.toml").write_text("new")
        rollback = tmp_path / "config-rollback"
        rollback.mkdir()
        (rollback / "config.toml").write_text("stale")

        atomic_promote_initial(config_root, candidate)

        assert (config_root / "config.toml").read_text() == "new"
        assert not rollback.exists()
        assert (tmp_path / "config.atomixos-promotion-pending").exists()


class TestRestoreRollback:
    def test_restores(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        (config_root / "config.toml").write_text("failed")
        rollback = tmp_path / "config-rollback"
        rollback.mkdir()
        (rollback / "config.toml").write_text("good")

        result = restore_rollback(config_root)
        assert result is True
        assert (config_root / "config.toml").read_text() == "good"

    def test_no_rollback(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        result = restore_rollback(config_root)
        assert result is False


class TestCleanupRollback:
    def test_removes_rollback(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        rollback = tmp_path / "config-rollback"
        rollback.mkdir()
        (rollback / "old.toml").write_text("old")
        cleanup_rollback(config_root)
        assert not rollback.exists()


class TestDiscardInitialConfig:
    def test_removes_active_and_staging_state(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        (config_root / "config.toml").write_text("failed")
        (config_root / "admin-signers").write_text("ssh-ed25519 AAAA key\n")
        candidate = tmp_path / "config-candidate"
        candidate.mkdir()
        rollback = tmp_path / "config-rollback"
        rollback.mkdir()
        marker = tmp_path / "config.atomixos-promotion-pending"
        marker.write_text("pending\n")

        discard_initial_config(config_root)

        assert not config_root.exists()
        assert not candidate.exists()
        assert not rollback.exists()
        assert not marker.exists()


class TestManagedState:
    def test_roundtrip(self, tmp_path):
        write_managed_state(tmp_path, {"user1", "user2"})
        result = read_managed_state(tmp_path)
        assert result == {"user1", "user2"}

    def test_carry_forward(self, tmp_path):
        prev = tmp_path / "prev"
        prev.mkdir()
        write_managed_state(prev, {"admin"})
        candidate = tmp_path / "candidate"
        candidate.mkdir()
        carry_forward_managed_state(prev, candidate)
        assert read_managed_state(candidate) == {"admin"}


class TestActivateServices:
    def test_no_env_var(self, monkeypatch):
        monkeypatch.delenv("ATOMIXOS_BOOTSTRAP_ACTIVATION", raising=False)
        assert activate_services() == []

    def test_script_not_found(self, monkeypatch):
        monkeypatch.setenv("ATOMIXOS_BOOTSTRAP_ACTIVATION", "/nonexistent/script")
        result = activate_services()
        assert "not found" in result[0]


class TestCheckRequiredServices:
    def test_no_health_file(self, tmp_path):
        assert check_required_services(tmp_path) == []

    def test_empty_list(self, tmp_path):
        (tmp_path / "health-required.json").write_text("[]")
        assert check_required_services(tmp_path) == []


class TestReportRuntimeServices:
    def test_reports_every_runtime_unit(self, tmp_path, monkeypatch):
        (tmp_path / "quadlet-runtime.json").write_text(
            json.dumps(
                {
                    "units": [
                        {"service": "web.service", "mode": "rootful"},
                        {"service": "worker.service", "mode": "rootless"},
                    ]
                }
            )
        )
        calls = []

        def fake_check_service(service, mode):
            calls.append((service, mode))
            return subprocess.CompletedProcess([], 0 if service == "web.service" else 3)

        monkeypatch.setattr(
            "atomixos_provision.activation._check_service", fake_check_service
        )
        progress = ProgressRecorder()

        statuses = report_runtime_services(tmp_path, progress)

        assert statuses == {"web.service": "running", "worker.service": "failed"}
        assert calls == [("web.service", "rootful"), ("worker.service", "rootless")]
        assert progress.stages == [
            (
                "service-status",
                "web.service (rootful) is running",
                {"service": "web.service", "mode": "rootful", "status": "running"},
            ),
            (
                "service-status",
                "worker.service (rootless) is failed",
                {"service": "worker.service", "mode": "rootless", "status": "failed"},
            ),
        ]

    def test_unknown_when_status_command_unavailable(self, tmp_path, monkeypatch):
        (tmp_path / "quadlet-runtime.json").write_text(
            json.dumps({"units": [{"service": "web.service", "mode": "rootful"}]})
        )

        def fake_check_service(_service, _mode):
            raise FileNotFoundError

        monkeypatch.setattr(
            "atomixos_provision.activation._check_service", fake_check_service
        )

        assert report_runtime_services(tmp_path) == {"web.service": "unknown"}


class TestReportRuntimeDeployStart:
    def test_reports_building_and_starting_units(self, tmp_path):
        (tmp_path / "quadlet-runtime.json").write_text(
            json.dumps(
                {
                    "units": [
                        {
                            "filename": "image.build",
                            "service": "image-build.service",
                            "mode": "rootful",
                        },
                        {
                            "filename": "web.container",
                            "service": "web.service",
                            "mode": "rootless",
                        },
                    ]
                }
            )
        )
        progress = ProgressRecorder()

        report_runtime_deploy_start(tmp_path, progress)

        assert progress.stages == [
            (
                "service-deploy",
                "image-build.service (rootful) building",
                {
                    "service": "image-build.service",
                    "mode": "rootful",
                    "status": "building",
                },
            ),
            (
                "service-deploy",
                "web.service (rootless) starting",
                {"service": "web.service", "mode": "rootless", "status": "starting"},
            ),
        ]


class TestCompleteReapply:
    def test_reports_deploy_status_before_required_health_checks(self, tmp_path, monkeypatch):
        config_root = tmp_path / "config"
        config_root.mkdir()
        rollback = tmp_path / "config-rollback"
        rollback.mkdir()
        (config_root / "quadlet-runtime.json").write_text(
            json.dumps({"units": [{"service": "web.service", "mode": "rootful"}]})
        )
        (config_root / "health-required.json").write_text(json.dumps(["web"]))
        progress = ProgressRecorder()

        monkeypatch.setattr("atomixos_provision.activation.activate_services", lambda _p: [])
        monkeypatch.setattr(
            "atomixos_provision.activation._check_service",
            lambda _service, _mode: subprocess.CompletedProcess([], 0),
        )

        assert complete_reapply(config_root, progress) == (True, [], "skipped")
        assert progress.stages[:3] == [
            (
                "service-deploy",
                "web.service (rootful) starting",
                {"service": "web.service", "mode": "rootful", "status": "starting"},
            ),
            (
                "service-status",
                "web.service (rootful) is running",
                {"service": "web.service", "mode": "rootful", "status": "running"},
            ),
            ("health-check", "checking web.service (rootful)", {}),
        ]

    def test_inactive_non_required_unit_does_not_fail_reapply(self, tmp_path, monkeypatch):
        config_root = tmp_path / "config"
        config_root.mkdir()
        rollback = tmp_path / "config-rollback"
        rollback.mkdir()
        (config_root / "quadlet-runtime.json").write_text(
            json.dumps({"units": [{"service": "sidecar.service", "mode": "rootful"}]})
        )
        progress = ProgressRecorder()

        monkeypatch.setattr("atomixos_provision.activation.activate_services", lambda _p: [])
        monkeypatch.setattr(
            "atomixos_provision.activation._check_service",
            lambda _service, _mode: subprocess.CompletedProcess([], 3),
        )

        assert complete_reapply(config_root, progress) == (True, [], "skipped")
        assert (
            "service-status",
            "sidecar.service (rootful) is failed",
            {"service": "sidecar.service", "mode": "rootful", "status": "failed"},
        ) in progress.stages

    def test_rollback_activation_failure_is_reported(self, tmp_path, monkeypatch):
        config_root = tmp_path / "config"
        config_root.mkdir()
        (config_root / "health-required.json").write_text(json.dumps(["web"]))
        rollback = tmp_path / "config-rollback"
        rollback.mkdir()
        (rollback / "config.toml").write_text("previous")
        calls = []

        def fake_activate(_progress):
            calls.append("activate")
            if len(calls) == 1:
                return []
            return ["activation script failed (exit 1): rollback"]

        monkeypatch.setattr("atomixos_provision.activation.activate_services", fake_activate)
        monkeypatch.setattr(
            "atomixos_provision.activation._check_service",
            lambda _service, _mode: subprocess.CompletedProcess([], 3),
        )

        success, failures, rollback_status = complete_reapply(config_root)

        assert success is False
        assert rollback_status == "failed"
        assert "web.service" in failures
        assert any("rollback activation/health failed" in failure for failure in failures)
        assert (config_root / "config.toml").read_text() == "previous"

    def test_rollback_health_failure_is_reported(self, tmp_path, monkeypatch):
        config_root = tmp_path / "config"
        config_root.mkdir()
        (config_root / "health-required.json").write_text(json.dumps(["web"]))
        rollback = tmp_path / "config-rollback"
        rollback.mkdir()
        (rollback / "config.toml").write_text("previous")
        (rollback / "health-required.json").write_text(json.dumps(["web"]))
        checks = []

        monkeypatch.setattr(
            "atomixos_provision.activation.activate_services", lambda _progress: []
        )

        def fake_check(service, _mode):
            checks.append(service)
            return subprocess.CompletedProcess([], 1)

        monkeypatch.setattr("atomixos_provision.activation._check_service", fake_check)

        success, failures, rollback_status = complete_reapply(config_root)

        assert success is False
        assert rollback_status == "failed"
        assert any(
            "rollback activation/health failed: web.service" in failure
            for failure in failures
        )
