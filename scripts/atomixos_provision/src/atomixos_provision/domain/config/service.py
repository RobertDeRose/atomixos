"""Config service facade."""

import asyncio
from pathlib import Path
from typing import Any

from atomixos_provision.jobs import Job

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

    async def stage_bytes(
        self,
        body: bytes,
        filename: str,
        progress: Job,
        allow_reapply: bool = True,
        authorization: dict[str, str] | None = None,
    ) -> None:
        """Stage raw configuration bytes for worker application."""
        from atomixos_provision.provision import stage_reserved_config_bytes

        await asyncio.to_thread(
            stage_reserved_config_bytes,
            progress.id,
            body,
            filename,
            self.config_root,
            allow_reapply=allow_reapply,
            progress=progress,
            authorization=authorization,
        )

    async def validate_bytes(self, body: bytes, filename: str) -> dict[str, Any]:
        """Validate raw configuration bytes without applying them."""
        from atomixos_provision.provision import validate_config_bytes

        return await validate_config_bytes(body, filename, self.config_root)

    async def export_config(self) -> bytes:
        """Export the current configuration under the provisioning lock."""
        from atomixos_provision.provision import locked_export_config_bytes

        return await asyncio.to_thread(locked_export_config_bytes, self.config_root)

    async def apply_partial(
        self,
        operation: dict[str, Any],
        progress: Job | None = None,
    ) -> dict[str, Any]:
        """Apply a typed partial configuration operation."""
        from atomixos_provision.provision import apply_config_operation

        return await apply_config_operation(operation, self.config_root, progress)

    async def stage_partial(
        self,
        operation: dict[str, Any],
        progress: Job,
        request_payload: bytes | None = None,
        authorization: dict[str, str] | None = None,
    ) -> None:
        """Stage a typed partial operation for worker application."""
        from atomixos_provision.provision import stage_reserved_config_operation

        await stage_reserved_config_operation(
            progress.id,
            operation,
            self.config_root,
            progress,
            request_payload,
            authorization,
        )

    async def put_user(self, name: str, payload: dict[str, Any], progress: Job | None = None):
        """Create or replace a user through a partial operation."""
        return await self.apply_partial(
            {"op": "put_user", "name": name, "payload": payload}, progress
        )

    async def delete_user(self, name: str, progress: Job | None = None):
        return await self.apply_partial({"op": "delete_user", "name": name}, progress)

    async def patch_network(self, payload: dict[str, Any], progress: Job | None = None):
        return await self.apply_partial({"op": "patch_network", "payload": payload}, progress)

    async def put_resource(
        self, table: str, name: str, payload: dict[str, Any], progress: Job | None = None
    ):
        return await self.apply_partial(
            {"op": "put_resource", "table": table, "name": name, "payload": payload},
            progress,
        )

    async def delete_resource(self, table: str, name: str, progress: Job | None = None):
        return await self.apply_partial(
            {"op": "delete_resource", "table": table, "name": name}, progress
        )
