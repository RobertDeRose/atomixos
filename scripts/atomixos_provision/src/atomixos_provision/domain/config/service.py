"""Config service facade."""

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

        return await apply_config_bytes(
            body, filename, self.config_root, progress, allow_reapply
        )

    async def validate_bytes(self, body: bytes, filename: str) -> dict[str, Any]:
        from atomixos_provision.provision import validate_config_bytes

        return await validate_config_bytes(body, filename, self.config_root)
