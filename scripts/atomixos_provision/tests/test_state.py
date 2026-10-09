"""Tests for the shared provisioning-state predicate."""

from atomixos_provision.state import is_provisioned_config_root


def test_provisioning_state_uses_marker_or_config(tmp_path):
    """Verify that provisioning state uses marker or config."""
    assert is_provisioned_config_root(tmp_path) is False

    (tmp_path / ".first-config").write_text("ok\n")
    assert is_provisioned_config_root(tmp_path) is True

    (tmp_path / ".first-config").unlink()
    (tmp_path / "config.toml").write_text("version = 1\n")
    assert is_provisioned_config_root(tmp_path) is True


def test_signer_file_alone_does_not_mark_config_root_provisioned(tmp_path):
    """Verify that signer file alone does not mark config root provisioned."""
    (tmp_path / "admin-signers").write_text("ssh-ed25519 AAAA test\n")

    assert is_provisioned_config_root(tmp_path) is False
