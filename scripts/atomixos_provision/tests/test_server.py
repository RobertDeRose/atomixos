"""Tests for atomixos_provision.server."""

from click.testing import CliRunner

from atomixos_provision import server


def test_serve_reads_environment_when_command_runs(monkeypatch, tmp_path):
    captured = {}

    class FakeUvicorn:
        @staticmethod
        def run(app, host, port, log_level):
            captured["app"] = app
            captured["host"] = host
            captured["port"] = port
            captured["log_level"] = log_level

    monkeypatch.setenv("ATOMIXOS_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setenv("ATOMIXOS_BOOTSTRAP_HOST", "127.0.0.1")
    monkeypatch.setenv("ATOMIXOS_BOOTSTRAP_PORT", "18080")
    monkeypatch.setitem(__import__("sys").modules, "uvicorn", FakeUvicorn)
    monkeypatch.setattr(server, "_get_systemd_socket", lambda: None)

    result = CliRunner().invoke(server.cli, ["serve"])

    assert result.exit_code == 0, result.output
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 18080
    assert captured["log_level"] == "info"
    assert captured["app"].state["config_root"] == tmp_path

def test_serve_uses_inherited_systemd_socket(monkeypatch, tmp_path):
    captured = {}

    class FakeSocket:
        def fileno(self):
            return 3

        def close(self):
            captured["closed"] = True

    class FakeConfig:
        def __init__(self, app, fd, log_level):
            captured["app"] = app
            captured["fd"] = fd
            captured["log_level"] = log_level

    class FakeServer:
        def __init__(self, config):
            captured["config"] = config

        async def serve(self):
            captured["served"] = True

    class FakeUvicorn:
        Config = FakeConfig
        Server = FakeServer

        @staticmethod
        def run(*_args, **_kwargs):
            raise AssertionError("serve should use inherited socket")

    monkeypatch.setenv("ATOMIXOS_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setitem(__import__("sys").modules, "uvicorn", FakeUvicorn)
    monkeypatch.setattr(server, "_get_systemd_socket", lambda: FakeSocket())

    result = CliRunner().invoke(server.cli, ["serve"])

    assert result.exit_code == 0, result.output
    assert captured["fd"] == 3
    assert captured["log_level"] == "info"
    assert captured["served"] is True
    assert captured["closed"] is True
    assert captured["app"].state["config_root"] == tmp_path


def test_apply_staged_command_returns_json(monkeypatch, tmp_path):
    captured = {}

    def fake_apply(config_root, runtime_root):
        captured["config_root"] = config_root
        captured["runtime_root"] = runtime_root
        return {"warnings": [], "reapply": False}

    monkeypatch.setattr("atomixos_provision.provision.apply_staged_job", fake_apply)

    result = CliRunner().invoke(
        server.cli,
        [
            "apply-staged",
            str(tmp_path / "config"),
            "--runtime-root",
            str(tmp_path / "run"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert '"ok": true' in result.output
    assert captured == {
        "config_root": tmp_path / "config",
        "runtime_root": tmp_path / "run",
    }


def test_apply_staged_command_drains_queue(monkeypatch, tmp_path):
    calls = []
    results = [
        {"warnings": ["first"], "reapply": False},
        {"warnings": ["second"], "reapply": True},
        None,
    ]

    def fake_apply(config_root, runtime_root):
        calls.append((config_root, runtime_root))
        return results.pop(0)

    monkeypatch.setattr("atomixos_provision.provision.apply_staged_job", fake_apply)

    result = CliRunner().invoke(
        server.cli,
        [
            "apply-staged",
            str(tmp_path / "config"),
            "--runtime-root",
            str(tmp_path / "run"),
            "--drain",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(calls) == 3
    assert '"warnings": ["first"]' in result.output
    assert '"warnings": ["second"]' in result.output


def test_apply_staged_command_drains_after_error(monkeypatch, tmp_path):
    calls = []
    outcomes = [RuntimeError("bad job"), {"warnings": ["second"]}, None]

    def fake_apply(config_root, runtime_root):
        calls.append((config_root, runtime_root))
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            outcome.staged_job_claimed = True
            raise outcome
        return outcome

    monkeypatch.setattr("atomixos_provision.provision.apply_staged_job", fake_apply)

    result = CliRunner().invoke(
        server.cli,
        [
            "apply-staged",
            str(tmp_path / "config"),
            "--runtime-root",
            str(tmp_path / "run"),
            "--drain",
        ],
    )

    assert result.exit_code == 1
    assert len(calls) == 3
    assert "bad job" in result.output
    assert '"warnings": ["second"]' in result.output


def test_apply_staged_command_stops_drain_after_systemic_error(monkeypatch, tmp_path):
    calls = []

    def fake_apply(config_root, runtime_root):
        calls.append((config_root, runtime_root))
        raise RuntimeError("runtime layout unavailable")

    monkeypatch.setattr("atomixos_provision.provision.apply_staged_job", fake_apply)

    result = CliRunner().invoke(
        server.cli,
        [
            "apply-staged",
            str(tmp_path / "config"),
            "--runtime-root",
            str(tmp_path / "run"),
            "--drain",
        ],
    )

    assert result.exit_code == 1
    assert len(calls) == 1
    assert "runtime layout unavailable" in result.output


def test_apply_staged_command_returns_json_error(monkeypatch, tmp_path):
    def fake_apply(config_root, runtime_root):
        raise RuntimeError("boom")

    monkeypatch.setattr("atomixos_provision.provision.apply_staged_job", fake_apply)

    result = CliRunner().invoke(
        server.cli,
        ["apply-staged", str(tmp_path / "config")],
    )

    assert result.exit_code == 1
    assert '"ok": false' in result.output
    assert "boom" in result.output


def test_finalize_staged_command_returns_json(monkeypatch, tmp_path):
    captured = {}

    def fake_finalize(runtime_root, reason):
        captured["runtime_root"] = runtime_root
        captured["reason"] = reason
        return 2

    monkeypatch.setattr("atomixos_provision.provision.finalize_staged_jobs", fake_finalize)

    result = CliRunner().invoke(
        server.cli,
        [
            "finalize-staged",
            "--runtime-root",
            str(tmp_path / "run"),
            "--reason",
            "worker stopped",
        ],
    )

    assert result.exit_code == 0, result.output
    assert '"ok": true' in result.output
    assert '"finalized": 2' in result.output
    assert captured == {"runtime_root": tmp_path / "run", "reason": "worker stopped"}


def test_recover_data_config_requires_worker_context(monkeypatch):
    monkeypatch.delenv("ATOMIXOS_PROVISION_WORKER_ACTIVE", raising=False)

    result = CliRunner().invoke(server.cli, ["recover", "/data/config"])

    assert result.exit_code != 0
    assert "requires privileged worker context" in str(result.exception)


def test_recover_grants_service_read_access(monkeypatch, tmp_path):
    config_root = tmp_path / "config"
    config_root.mkdir()
    config_path = config_root / "config.toml"
    config_path.write_text("version = 1\n", encoding="utf-8")
    config_path.chmod(0o600)
    monkeypatch.setattr("atomixos_provision.provision._service_identity", lambda: (123, 456))
    monkeypatch.setattr("atomixos_provision.provision.os.chown", lambda *_args, **_kwargs: None)

    result = CliRunner().invoke(server.cli, ["recover", str(config_root)])

    assert result.exit_code == 0, result.output
    assert config_path.stat().st_mode & 0o040


def test_complete_initial_data_config_requires_worker_context(monkeypatch):
    monkeypatch.delenv("ATOMIXOS_PROVISION_WORKER_ACTIVE", raising=False)

    result = CliRunner().invoke(server.cli, ["complete-initial", "/data/config"])

    assert result.exit_code != 0
    assert "requires privileged worker context" in str(result.exception)
