"""Shared test fixtures for atomixos_provision."""

import os
import stat
import sys

import pytest

from atomixos_provision import bundle
from atomixos_provision.config import provision_error


@pytest.fixture(autouse=True)
def allow_test_config_roots(monkeypatch):
    """Allow temp config roots in tests; production is restricted to /data/config."""
    monkeypatch.setenv("ATOMIXOS_ALLOW_UNSAFE_CONFIG_ROOT", "1")


@pytest.fixture(autouse=True)
def host_regular_file_open(monkeypatch):
    """Emulate the Linux file-open boundary for ordinary Darwin host tests.

    This stand-in preserves descriptor validation for higher-level tests; it
    does not exercise Linux's non-opening handle or procfs inode pinning.
    """
    original = bundle._open_verified_regular_file
    if sys.platform == "darwin":

        def open_regular_file(name, parent_fd, expected, path, changed_message):
            fd = os.open(
                name,
                os.O_RDONLY | os.O_NONBLOCK | bundle.OPEN_NOFOLLOW,
                dir_fd=parent_fd,
            )
            try:
                confirmed = os.fstat(fd)
                if not stat.S_ISREG(confirmed.st_mode) or confirmed.st_nlink != 1:
                    raise provision_error(
                        f"bundle entry must be a single-link regular file: {path}"
                    )
                if (confirmed.st_dev, confirmed.st_ino) != (expected.st_dev, expected.st_ino):
                    raise provision_error(changed_message)
                return fd
            except Exception:
                os.close(fd)
                raise

        monkeypatch.setattr(bundle, "_open_verified_regular_file", open_regular_file)
    return original


@pytest.fixture
def native_file_open(monkeypatch, host_regular_file_open):
    """Use the production Linux boundary, including its unsupported-host error."""
    monkeypatch.setattr(bundle, "_open_verified_regular_file", host_regular_file_open)
