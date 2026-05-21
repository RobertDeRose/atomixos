"""Litestar dependency providers for the provisioning service."""

from pathlib import Path

from litestar.datastructures import State

from atomixos_provision.auth import NonceStore
from atomixos_provision.domain.config.service import ConfigService
from atomixos_provision.jobs import JobManager
from atomixos_provision.settings import AppSettings

__all__ = [
    "provide_config_root",
    "provide_config_service",
    "provide_job_manager",
    "provide_nonce_store",
    "provide_settings",
]


def provide_settings(state: State) -> AppSettings:
    """Provide application settings from Litestar state."""
    return state.settings


def provide_config_root(settings: AppSettings) -> Path:
    """Provide the active config root path."""
    return settings.config_root


def provide_config_service(config_root: Path) -> ConfigService:
    """Provide a config service facade."""
    return ConfigService(config_root)


def provide_nonce_store(state: State) -> NonceStore:
    """Provide the nonce store from Litestar state."""
    return state.nonce_store


def provide_job_manager(state: State) -> JobManager:
    """Provide the job manager from Litestar state."""
    return state.job_manager
