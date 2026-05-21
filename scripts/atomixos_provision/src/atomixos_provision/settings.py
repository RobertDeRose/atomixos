"""Application settings for the provisioning service."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from atomixos_provision.bundle import MAX_SOURCE_BYTES

__all__ = ["AppSettings"]


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class AppSettings:
    """Small environment-backed settings object for Litestar app construction."""

    config_root: Path = field(
        default_factory=lambda: Path(os.environ.get("ATOMIXOS_CONFIG_ROOT", "/data/config"))
    )
    host: str = field(
        default_factory=lambda: os.environ.get("ATOMIXOS_BOOTSTRAP_HOST", "172.20.30.1")
    )
    port: int = field(default_factory=lambda: _env_int("ATOMIXOS_BOOTSTRAP_PORT", 8080))
    max_source_bytes: int = MAX_SOURCE_BYTES
