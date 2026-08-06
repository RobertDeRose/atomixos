"""Shared provisioning-state predicates."""

import stat
from pathlib import Path

FIRST_CONFIG_MARKER = ".first-config"


def _is_regular_file(path: Path) -> bool:
    """Return whether a path is a regular file without following symlinks."""
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return False
    return stat.S_ISREG(mode)


def is_provisioned_config_root(config_root: Path) -> bool:
    """Return whether a config root has entered the provisioned state."""
    return _is_regular_file(config_root / FIRST_CONFIG_MARKER) or _is_regular_file(
        config_root / "config.toml"
    )
