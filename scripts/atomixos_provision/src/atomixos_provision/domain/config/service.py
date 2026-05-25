"""Config service facade."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from atomixos_provision.jobs import Job
from atomixos_provision.partial_config import (
    delete_resource,
    delete_user,
    patch_network,
    put_resource,
    put_user,
)

__all__ = ["ConfigService"]


class ConfigService:
    """Facade for config validation and provisioning operations."""

    def __init__(self, config_root: Path) -> None:
        self.config_root = config_root

    async def apply_bytes(
        self,
        body: bytes,
        filename: str,
        progress: Job | None = None,
        allow_reapply: bool = True,
    ) -> dict[str, Any]:
        from atomixos_provision.provision import apply_config_bytes

        return await apply_config_bytes(body, filename, self.config_root, progress, allow_reapply)

    async def validate_bytes(self, body: bytes, filename: str) -> dict[str, Any]:
        from atomixos_provision.provision import validate_config_bytes

        return await validate_config_bytes(body, filename, self.config_root)

    def export_config(self) -> bytes:
        from atomixos_provision.provision import locked_export_config_bytes

        return locked_export_config_bytes(self.config_root)

    async def apply_partial(
        self,
        transform: Callable[[dict[str, Any]], dict[str, Any]],
        progress: Job | None = None,
    ) -> dict[str, Any]:
        from atomixos_provision.provision import apply_config_transform

        return await apply_config_transform(transform, self.config_root, progress)

    async def put_user(self, name: str, payload: dict[str, Any], progress: Job | None = None):
        return await self.apply_partial(lambda config: put_user(config, name, payload), progress)

    async def delete_user(self, name: str, progress: Job | None = None):
        return await self.apply_partial(lambda config: delete_user(config, name), progress)

    async def patch_network(self, payload: dict[str, Any], progress: Job | None = None):
        return await self.apply_partial(lambda config: patch_network(config, payload), progress)

    async def put_resource(
        self, table: str, name: str, payload: dict[str, Any], progress: Job | None = None
    ):
        return await self.apply_partial(
            lambda config: put_resource(config, table, name, payload), progress
        )

    async def delete_resource(self, table: str, name: str, progress: Job | None = None):
        return await self.apply_partial(
            lambda config: delete_resource(config, table, name), progress
        )
