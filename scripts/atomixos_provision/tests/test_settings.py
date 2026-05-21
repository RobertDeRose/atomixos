"""Tests for atomixos_provision.settings."""

from pathlib import Path

from atomixos_provision.settings import AppSettings


def test_default_settings_match_device_defaults():
    settings = AppSettings()

    assert settings.config_root == Path("/data/config")
    assert settings.host == "172.20.30.1"
    assert settings.port == 8080
    assert settings.max_source_bytes > 0


def test_settings_read_environment_per_instance(monkeypatch, tmp_path):
    first = AppSettings()
    monkeypatch.setenv("ATOMIXOS_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setenv("ATOMIXOS_BOOTSTRAP_HOST", "127.0.0.1")
    monkeypatch.setenv("ATOMIXOS_BOOTSTRAP_PORT", "18080")

    second = AppSettings()

    assert first.config_root != tmp_path
    assert second.config_root == tmp_path
    assert second.host == "127.0.0.1"
    assert second.port == 18080


def test_create_app_stores_settings(tmp_path):
    from atomixos_provision.app import create_app

    settings = AppSettings(config_root=tmp_path, host="127.0.0.1", port=18080)
    app = create_app(settings=settings)

    assert app.state["settings"] == settings
    assert app.state["config_root"] == tmp_path
