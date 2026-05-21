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
