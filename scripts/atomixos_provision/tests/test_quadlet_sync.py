"""Tests for atomixos_provision.quadlet_sync module."""

import json
from pathlib import Path

import pytest

from atomixos_provision.config import ProvisionError
from atomixos_provision.quadlet_sync import load_runtime_metadata, sync_quadlet_units


@pytest.fixture()
def config_root(tmp_path: Path) -> Path:
    """Set up a config root with quadlet dir and runtime metadata."""
    quadlet_dir = tmp_path / "quadlet"
    quadlet_dir.mkdir()
    # Write a container unit
    (quadlet_dir / "myapp.container").write_text("[Container]\nImage=alpine\n")
    # Write runtime metadata
    metadata = {
        "app_user": "appsvc",
        "rootless_network": "pasta",
        "units": [
            {
                "name": "myapp",
                "filename": "myapp.container",
                "service": "myapp.service",
                "mode": "rootful",
            }
        ],
    }
    (tmp_path / "quadlet-runtime.json").write_text(json.dumps(metadata))
    return tmp_path


class TestLoadRuntimeMetadata:
    def test_valid(self, config_root):
        metadata = load_runtime_metadata(config_root)
        assert len(metadata["units"]) == 1

    def test_missing_file(self, tmp_path):
        with pytest.raises(ProvisionError, match="missing runtime metadata"):
            load_runtime_metadata(tmp_path)

    def test_invalid_json(self, tmp_path):
        (tmp_path / "quadlet-runtime.json").write_text("not json")
        with pytest.raises(ProvisionError, match="invalid runtime metadata"):
            load_runtime_metadata(tmp_path)

    def test_bad_structure(self, tmp_path):
        (tmp_path / "quadlet-runtime.json").write_text('{"units": "not a list"}')
        with pytest.raises(ProvisionError, match="invalid runtime metadata structure"):
            load_runtime_metadata(tmp_path)


class TestSyncQuadletUnits:
    def test_copies_rootful(self, config_root, tmp_path):
        target = tmp_path / "rootful"
        sync_quadlet_units(config_root, target)
        assert (target / "myapp.container").exists()
        assert (target / "myapp.container").read_text() == "[Container]\nImage=alpine\n"

    def test_removes_stale(self, config_root, tmp_path):
        target = tmp_path / "rootful"
        target.mkdir()
        (target / "old.container").write_text("stale")
        (target / ".atomixos-managed-quadlets.json").write_text(
            json.dumps(["old.container"])
        )
        sync_quadlet_units(config_root, target)
        assert not (target / "old.container").exists()
        assert (target / "myapp.container").exists()

    def test_preserves_unmanaged_quadlets(self, config_root, tmp_path):
        target = tmp_path / "rootful"
        target.mkdir()
        (target / "admin.container").write_text("unmanaged")

        sync_quadlet_units(config_root, target)

        assert (target / "admin.container").read_text() == "unmanaged"
        manifest = json.loads((target / ".atomixos-managed-quadlets.json").read_text())
        assert manifest == ["myapp.container"]

    def test_replaces_existing_unit_atomically(self, config_root, tmp_path):
        target = tmp_path / "rootful"
        target.mkdir()
        unit_path = target / "myapp.container"
        unit_path.write_text("[Container]\nImage=old\n")

        sync_quadlet_units(config_root, target)

        assert unit_path.read_text() == "[Container]\nImage=alpine\n"
        assert unit_path.stat().st_mode & 0o777 == 0o644
        assert not list(target.glob(".myapp.container.*"))

    def test_rootless_required_when_units_present(self, tmp_path):
        quadlet_dir = tmp_path / "quadlet"
        quadlet_dir.mkdir()
        (quadlet_dir / "app.container").write_text("[Container]\nImage=x\n")
        metadata = {
            "units": [
                {
                    "name": "app",
                    "filename": "app.container",
                    "service": "app.service",
                    "mode": "rootless",
                }
            ]
        }
        (tmp_path / "quadlet-runtime.json").write_text(json.dumps(metadata))
        rootful_target = tmp_path / "rootful"
        with pytest.raises(ProvisionError, match="rootless target path is required"):
            sync_quadlet_units(tmp_path, rootful_target, rootless_target=None)

    def test_rootless_sync(self, tmp_path):
        quadlet_dir = tmp_path / "quadlet"
        quadlet_dir.mkdir()
        (quadlet_dir / "app.container").write_text("[Container]\nImage=x\n")
        metadata = {
            "units": [
                {
                    "name": "app",
                    "filename": "app.container",
                    "service": "app.service",
                    "mode": "rootless",
                }
            ]
        }
        (tmp_path / "quadlet-runtime.json").write_text(json.dumps(metadata))
        rootful_target = tmp_path / "rootful"
        rootless_target = tmp_path / "rootless"
        sync_quadlet_units(tmp_path, rootful_target, rootless_target)
        assert (rootless_target / "app.container").exists()

    def test_rejects_runtime_filename_escape(self, tmp_path):
        quadlet_dir = tmp_path / "quadlet"
        quadlet_dir.mkdir()
        (tmp_path / "quadlet-runtime.json").write_text(
            json.dumps(
                {
                    "units": [
                        {
                            "name": "app",
                            "filename": "../app.container",
                            "service": "app.service",
                            "mode": "rootful",
                        }
                    ]
                }
            )
        )
        with pytest.raises(ProvisionError, match="invalid runtime unit filename"):
            sync_quadlet_units(tmp_path, tmp_path / "rootful")
