"""Tests for atomixos_provision.exceptions."""

from atomixos_provision.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationApiError,
    api_error_response,
)


def test_api_error_response_maps_status_and_body():
    response = api_error_response(ConflictError("busy"))

    assert response.status_code == 409
    assert response.content == {"error": "busy"}


def test_not_found_error_maps_status_and_body():
    response = api_error_response(NotFoundError("missing"))

    assert response.status_code == 404
    assert response.content == {"error": "missing"}


def test_validation_error_preserves_ok_false_shape():
    response = api_error_response(ValidationApiError("invalid"))

    assert response.status_code == 400
    assert response.content == {"ok": False, "error": "invalid"}
