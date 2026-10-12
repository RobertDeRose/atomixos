"""Shared provisioning-state predicates."""

import stat
from pathlib import Path

FIRST_CONFIG_MARKER = ".first-config"


def _is_regular_file(path: Path) -> bool:
    """Return whether a path is a regular file without following symlinks."""
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    return stat.S_ISREG(mode)


def is_provisioned_config_root(config_root: Path) -> bool:
    """Return whether .first-config or config.toml is a regular file.

    Missing files and symlinks do not establish provisioning; other filesystem
    errors propagate. An admin-signers file alone does not mark the root as
    provisioned.
    """
    return _is_regular_file(config_root / FIRST_CONFIG_MARKER) or _is_regular_file(
        config_root / "config.toml"
    )
