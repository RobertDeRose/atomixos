"""Shared test fixtures for atomixos_provision."""

import pytest


@pytest.fixture(autouse=True)
def allow_test_config_roots(monkeypatch):
    """Allow temp config roots in tests; production is restricted to /data/config."""
    monkeypatch.setenv("ATOMIXOS_ALLOW_UNSAFE_CONFIG_ROOT", "1")
