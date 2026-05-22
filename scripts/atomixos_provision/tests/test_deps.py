"""Tests for atomixos_provision.deps."""

from litestar.datastructures import State

from atomixos_provision.auth import NonceStore
from atomixos_provision.deps import (
    provide_config_root,
    provide_config_service,
    provide_job_manager,
    provide_nonce_store,
    provide_settings,
)
from atomixos_provision.domain.config.service import ConfigService
from atomixos_provision.jobs import JobManager
from atomixos_provision.settings import AppSettings


async def test_dependency_providers_return_state_objects(tmp_path):
    settings = AppSettings(config_root=tmp_path)
    nonce_store = NonceStore()
    job_manager = JobManager()
    state = State(
        {
            "settings": settings,
            "nonce_store": nonce_store,
            "job_manager": job_manager,
        }
    )

    assert provide_settings(state) is settings
    assert provide_config_root(settings) == tmp_path
    assert isinstance(provide_config_service(tmp_path), ConfigService)
    assert provide_config_service(tmp_path).config_root == tmp_path
    assert provide_nonce_store(state) is nonce_store
    assert provide_job_manager(state) is job_manager
