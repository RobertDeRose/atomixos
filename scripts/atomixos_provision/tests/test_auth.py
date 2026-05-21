"""Tests for atomixos_provision.auth module."""

from pathlib import Path
from unittest.mock import patch

import pytest
from litestar.exceptions import NotAuthorizedException

from atomixos_provision.auth import (
    NonceStore,
    SignerState,
    build_allowed_signers,
    reapply_signature_message,
    ssh_auth_guard,
    verify_ssh_signature,
)


class _AcceptingNonceStore:
    async def consume(self, _nonce: str) -> bool:
        return True


class TestNonceStore:
    @pytest.fixture()
    def store(self):
        return NonceStore(ttl=5)

    @pytest.mark.asyncio
    async def test_issue_and_consume(self, store):
        nonce = await store.issue()
        assert isinstance(nonce, str)
        assert len(nonce) > 20
        assert await store.consume(nonce) is True

    @pytest.mark.asyncio
    async def test_consume_invalid(self, store):
        assert await store.consume("nonexistent") is False

    @pytest.mark.asyncio
    async def test_single_use(self, store):
        nonce = await store.issue()
        assert await store.consume(nonce) is True
        assert await store.consume(nonce) is False

    @pytest.mark.asyncio
    async def test_expired_nonce(self):
        store = NonceStore(ttl=0)
        nonce = await store.issue()
        # TTL is 0, so it's immediately expired
        assert await store.consume(nonce) is False

    @pytest.mark.asyncio
    async def test_evicts_oldest_when_outstanding_limit_reached(self):
        store = NonceStore(ttl=60, max_outstanding=2)
        first = await store.issue("a")
        second = await store.issue("b")
        third = await store.issue("c")

        assert await store.consume(first) is False
        assert await store.consume(second) is True
        assert await store.consume(third) is True

    @pytest.mark.asyncio
    async def test_outstanding_limit_has_minimum_one(self):
        store = NonceStore(ttl=60, max_outstanding=0)
        first = await store.issue()
        second = await store.issue()

        assert await store.consume(first) is False
        assert await store.consume(second) is True

    @pytest.mark.asyncio
    async def test_per_client_limit_does_not_evict_other_clients(self, monkeypatch):
        monkeypatch.setattr("atomixos_provision.auth.MAX_OUTSTANDING_NONCES_PER_CLIENT", 2)
        store = NonceStore(ttl=60, max_outstanding=10)
        first = await store.issue("client-a")
        second = await store.issue("client-b")
        third = await store.issue("client-a")
        fourth = await store.issue("client-a")

        assert await store.consume(first) is False
        assert await store.consume(second) is True
        assert await store.consume(third) is True
        assert await store.consume(fourth) is True


class TestReapplySignatureMessage:
    def test_format(self):
        msg = reapply_signature_message("nonce123", "/api/config", b"hello")
        assert msg.startswith("atomixos-reapply-v1\n")
        assert "nonce:nonce123\n" in msg
        assert "path:/api/config\n" in msg
        assert "sha256:" in msg

    def test_deterministic(self):
        msg1 = reapply_signature_message("n", "/p", b"data")
        msg2 = reapply_signature_message("n", "/p", b"data")
        assert msg1 == msg2

    def test_different_payload(self):
        msg1 = reapply_signature_message("n", "/p", b"a")
        msg2 = reapply_signature_message("n", "/p", b"b")
        assert msg1 != msg2


class TestBuildAllowedSigners:
    def test_no_file(self, tmp_path):
        result = build_allowed_signers(tmp_path)
        assert result is None

    def test_empty_file(self, tmp_path):
        (tmp_path / "admin-signers").write_text("")
        result = build_allowed_signers(tmp_path)
        assert result is None

    def test_with_keys(self, tmp_path):
        (tmp_path / "admin-signers").write_text(
            "ssh-ed25519 AAAA key1\nssh-rsa BBBB key2\n"
        )
        result = build_allowed_signers(tmp_path)
        assert result is not None
        content = Path(result).read_text()
        assert "atomixos-reapply ssh-ed25519 AAAA key1" in content
        assert "atomixos-reapply ssh-rsa BBBB key2" in content
        Path(result).unlink()


class TestVerifySshSignature:
    def test_missing_binary(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.write_text("atomixos-reapply ssh-ed25519 AAAA key\n")
        with patch(
            "atomixos_provision.auth.SSH_KEYGEN_BIN",
            "/nonexistent/ssh-keygen",
        ):
            result = verify_ssh_signature("msg", b"sig", allowed)
        assert result is False


class _Headers(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


class _Connection:
    def __init__(self, tmp_path, signature: str):
        (tmp_path / "admin-signers").write_text("ssh-ed25519 AAAA test\n")
        self.headers = _Headers({
            "x-atomixos-nonce": "nonce",
            "x-atomixos-signature": signature,
        })
        self.url = type("URL", (), {"path": "/api/config"})()
        self.app = type(
            "App",
            (),
            {
                "state": type(
                    "State",
                    (),
                    {
                        "config_root": tmp_path,
                        "signer_state": SignerState(initialized=True),
                        "nonce_store": _AcceptingNonceStore(),
                    },
                )(),
            },
        )()

    async def body(self):
        return b"payload"


class _UnsignedConnection:
    def __init__(self, tmp_path, initialized: bool = False):
        self.headers = _Headers({})
        self.url = type("URL", (), {"path": "/api/config"})()
        self.app = type(
            "App",
            (),
            {
                "state": type(
                    "State",
                    (),
                    {
                        "config_root": tmp_path,
                        "signer_state": SignerState(initialized=initialized),
                        "nonce_store": _AcceptingNonceStore(),
                    },
                )(),
            },
        )()

    async def body(self):
        return b"payload"


@pytest.mark.asyncio
async def test_auth_guard_rejects_non_strict_base64_signature(tmp_path):
    connection = _Connection(tmp_path, "not valid base64!!!!")

    with pytest.raises(NotAuthorizedException, match="invalid signature encoding"):
        await ssh_auth_guard(connection, None)


@pytest.mark.asyncio
async def test_auth_guard_allows_unprovisioned_without_signers(tmp_path):
    connection = _UnsignedConnection(tmp_path)

    await ssh_auth_guard(connection, None)


@pytest.mark.asyncio
async def test_auth_guard_fails_closed_when_provisioned_signers_missing(tmp_path):
    (tmp_path / "config.toml").write_text("version = 1\n")
    connection = _UnsignedConnection(tmp_path)

    with pytest.raises(NotAuthorizedException, match="admin signers"):
        await ssh_auth_guard(connection, None)
