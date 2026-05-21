"""Domain exceptions and HTTP response mapping."""

from http import HTTPStatus
from typing import Any

from litestar.response import Response

__all__ = [
    "ApiError",
    "ConflictError",
    "NotFoundError",
    "ValidationApiError",
    "api_error_response",
]


class ApiError(RuntimeError):
    """Base class for domain errors returned by API routes."""

    status_code = HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def body(self) -> dict[str, Any]:
        return {"error": self.message}


class ConflictError(ApiError):
    """Raised when a request conflicts with current service state."""

    status_code = HTTPStatus.CONFLICT


class NotFoundError(ApiError):
    """Raised when a requested resource does not exist."""

    status_code = HTTPStatus.NOT_FOUND


class ValidationApiError(ApiError):
    """Raised when submitted configuration fails validation."""

    status_code = HTTPStatus.BAD_REQUEST

    ok = False

    def body(self) -> dict[str, Any]:
        return {"ok": self.ok, "error": self.message}


def api_error_response(exc: ApiError) -> Response[dict[str, Any]]:
    """Convert a domain exception to a Litestar response."""
    return Response(exc.body(), status_code=exc.status_code)
