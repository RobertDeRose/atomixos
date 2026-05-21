"""System API routes."""

from litestar import get

__all__ = ["health"]


@get(
    "/api/health",
    operation_id="systemHealth",
    summary="Check provisioning service health",
    tags=["system"],
)
async def health() -> dict[str, str]:
    """GET /api/health — liveness check."""
    return {"status": "ok"}
