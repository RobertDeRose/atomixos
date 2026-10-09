"""Regression coverage for nixfmt lock normalization."""

import importlib.util
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "setup_tooling", Path(__file__).resolve().parents[1] / "scripts/setup-tooling.py"
)
setup_tooling = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(setup_tooling)

TOOL = "aqua:Mic92/nixfmt-rs"


def normalize(root, platforms):
    (root / "mise.toml").write_text(f'[tools]\n"{TOOL}" = "latest"\n')
    lock = root / "mise.lock"
    lock.write_text(
        f'[[tools."{TOOL}"]]\nversion = "0.5.3"\n'
        + "".join(
            f'[tools."{TOOL}"."platforms.{platform}"]\nchecksum = "test"\n'
            for platform in platforms
        )
        + '[tools.hk]\nversion = "2.0.1"\n'
    )
    original = lock.read_text()
    error = setup_tooling.normalize_nixfmt_lock(root, lock)
    return error, original, lock.read_text()


def test_removes_unsupported_platform_without_changing_other_tools(tmp_path):
    error, original, normalized = normalize(
        tmp_path, ["linux-x64", "macos-x64", "linux-arm64", "macos-arm64"]
    )
    assert error is None
    assert normalized == original.replace(
        f'[tools."{TOOL}"."platforms.macos-x64"]\nchecksum = "test"\n', ""
    )


@pytest.mark.parametrize("missing", ["linux-x64", "linux-arm64", "macos-arm64"])
def test_rejects_each_missing_supported_platform_without_modifying_lock(tmp_path, missing):
    required = ["linux-x64", "linux-arm64", "macos-arm64"]
    error, original, normalized = normalize(
        tmp_path, [platform for platform in required if platform != missing] + ["macos-x64"]
    )
    assert error == f"mise lock omitted nixfmt-rs for supported platforms: {missing}"
    assert normalized == original


def test_keeps_supported_lock_unchanged(tmp_path):
    error, original, normalized = normalize(tmp_path, ["linux-x64", "linux-arm64", "macos-arm64"])
    assert error is None
    assert normalized == original
