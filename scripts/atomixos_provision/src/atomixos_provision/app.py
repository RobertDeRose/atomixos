"""Litestar application factory and route wiring."""

import secrets
from pathlib import Path

from litestar import Litestar
from litestar.datastructures import State
from litestar.di import Provide

from atomixos_provision.auth import NonceStore, SignerState
from atomixos_provision.deps import (
    provide_config_root,
    provide_config_service,
    provide_job_manager,
    provide_nonce_store,
    provide_settings,
)
from atomixos_provision.domain.auth.controller import nonce
from atomixos_provision.domain.config.controller import (
    delete_container,
    delete_container_network,
    delete_container_volume,
    delete_partial_user,
    export_config,
    patch_partial_network,
    put_container,
    put_container_network,
    put_container_volume,
    put_partial_user,
    submit_config,
    validate_config,
)
from atomixos_provision.domain.jobs.controller import get_job
from atomixos_provision.domain.system.controller import health
from atomixos_provision.jobs import JobManager
from atomixos_provision.settings import AppSettings
from atomixos_provision.ui import ui_routes

__all__ = ["create_app"]

DEFAULT_CONFIG_ROOT = Path("/data/config")


def create_app(
    config_root: Path | None = None,
    settings: AppSettings | None = None,
    nonce_store: NonceStore | None = None,
    job_manager: JobManager | None = None,
) -> Litestar:
    """Create the Litestar application with all routes."""
    if settings is None:
        settings = AppSettings() if config_root is None else AppSettings(config_root=config_root)
    elif config_root is not None:
        settings = AppSettings(
            config_root=config_root,
            host=settings.host,
            port=settings.port,
            max_source_bytes=settings.max_source_bytes,
        )
    config_root = settings.config_root
    if nonce_store is None:
        nonce_store = NonceStore()
    if job_manager is None:
        job_manager = JobManager()
    signer_state = SignerState((config_root / "admin-signers").exists())

    app = Litestar(
        route_handlers=[
            health,
            nonce,
            submit_config,
            export_config,
            put_partial_user,
            delete_partial_user,
            patch_partial_network,
            put_container,
            delete_container,
            put_container_network,
            delete_container_network,
            put_container_volume,
            delete_container_volume,
            get_job,
            validate_config,
            *ui_routes(),
        ],
        state=State(
            {
                "config_root": config_root,
                "nonce_store": nonce_store,
                "job_manager": job_manager,
                "signer_state": signer_state,
                "settings": settings,
                "bootstrap_token": secrets.token_urlsafe(32),
            }
        ),
        dependencies={
            "settings": Provide(provide_settings, sync_to_thread=False),
            "config_root": Provide(provide_config_root, sync_to_thread=False),
            "config_service": Provide(provide_config_service, sync_to_thread=False),
            "nonce_store": Provide(provide_nonce_store, sync_to_thread=False),
            "job_manager": Provide(provide_job_manager, sync_to_thread=False),
        },
        request_max_body_size=settings.max_source_bytes,
    )

    return app
