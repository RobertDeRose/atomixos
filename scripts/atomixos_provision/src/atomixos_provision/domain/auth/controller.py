"""Authentication API routes."""

from litestar import Request, get

from atomixos_provision.auth import NonceStore
from atomixos_provision.schemas import NonceResponse, NonceResponseBody, schema_dict

__all__ = ["nonce"]


@get(
    "/api/nonce",
    operation_id="authIssueNonce",
    summary="Issue a single-use SSH signature nonce",
    tags=["auth"],
)
async def nonce(request: Request, nonce_store: NonceStore) -> NonceResponseBody:
    """GET /api/nonce — issue a single-use authentication nonce."""
    client = request.client
    client_id = client.host if client else ""
    value = await nonce_store.issue(client_id)
    return schema_dict(NonceResponse(nonce=value))
