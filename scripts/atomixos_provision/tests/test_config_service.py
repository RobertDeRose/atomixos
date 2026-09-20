"""Tests for the config service facade."""

from atomixos_provision.domain.config.service import ConfigService


def _write_current_config(tmp_path):
    (tmp_path / "config.toml").write_text(
        """\
version = 1

[users.admin]
isAdmin = true
ssh_key = "ssh-ed25519 AAAA admin"

[activation]
required = ["app"]

[containers.container.app]
privileged = false

[containers.container.app.Container]
Image = "alpine"
"""
    )


async def test_put_user_applies_config_operation(tmp_path, monkeypatch):
    _write_current_config(tmp_path)
    captured = {}

    async def fake_apply_config_operation(operation, config_root, progress=None):
        captured["operation"] = operation
        captured["config_root"] = config_root
        return {"warnings": []}

    monkeypatch.setattr(
        "atomixos_provision.provision.apply_config_operation",
        fake_apply_config_operation,
    )

    result = await ConfigService(tmp_path).put_user(
        "alice", {"isAdmin": False, "ssh_key": "ssh-ed25519 AAAA alice"}
    )

    assert result == {"warnings": []}
    assert captured["config_root"] == tmp_path
    assert captured["operation"] == {
        "op": "put_user",
        "name": "alice",
        "payload": {"isAdmin": False, "ssh_key": "ssh-ed25519 AAAA alice"},
    }


async def test_export_config_reads_current_bundle_bytes(tmp_path):
    """Verify that export config reads current bundle bytes."""
    _write_current_config(tmp_path)
    (tmp_path / "files").mkdir()
    (tmp_path / "files" / "cert.pem").write_text("CERT\n")

    body = await ConfigService(tmp_path).export_config()

    assert body.startswith(b"\x1f\x8b")


async def test_export_config_uses_locked_export(tmp_path, monkeypatch):
    """Verify that export config uses locked export."""
    captured = {}

    def fake_locked_export_config_bytes(config_root):
        captured["config_root"] = config_root
        return b"\x1f\x8bexported-bundle"

    monkeypatch.setattr(
        "atomixos_provision.provision.locked_export_config_bytes",
        fake_locked_export_config_bytes,
    )

    body = await ConfigService(tmp_path).export_config()

    assert body == b"\x1f\x8bexported-bundle"
    assert captured["config_root"] == tmp_path
