"""SSH signature verification guard and nonce manager."""

import asyncio
import base64
import hashlib
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException
from litestar.handlers import BaseRouteHandler

__all__ = [
    "NonceStore",
    "SignerState",
    "build_allowed_signers",
    "reapply_signature_message",
    "ssh_auth_guard",
    "ssh_auth_required_guard",
    "verify_ssh_signature",
]

# --- Configuration ---

NONCE_TTL_SECONDS = int(os.environ.get("ATOMIXOS_NONCE_TTL", "300"))
MAX_OUTSTANDING_NONCES = int(os.environ.get("ATOMIXOS_MAX_OUTSTANDING_NONCES", "1024"))
MAX_OUTSTANDING_NONCES_PER_CLIENT = int(
    os.environ.get("ATOMIXOS_MAX_OUTSTANDING_NONCES_PER_CLIENT", "16")
)
SSH_KEYGEN_BIN = os.environ.get("ATOMIXOS_SSH_KEYGEN", "ssh-keygen")
AUTH_REQUIRED_MESSAGE = (
    "authentication required: provide X-AtomixOS-Nonce and X-AtomixOS-Signature headers"
)


# --- Nonce Store ---


class NonceStore:
    """Thread-safe in-memory store for short-lived authentication nonces."""

    def __init__(
        self,
        ttl: int = NONCE_TTL_SECONDS,
        max_outstanding: int = MAX_OUTSTANDING_NONCES,
    ):
        self._ttl = ttl
        self._max_outstanding = max(1, max_outstanding)
        self._nonces: dict[str, tuple[float, str]] = {}
        self._lock = asyncio.Lock()

    async def issue(self, client_id: str = "") -> str:
        """Issue a new single-use nonce."""
        async with self._lock:
            self._prune()
            self._evict_client_over_limit(client_id)
            self._evict_over_limit()
            nonce = secrets.token_urlsafe(32)
            self._nonces[nonce] = (time.monotonic(), client_id)
            return nonce

    async def consume(self, nonce: str) -> bool:
        """Consume a nonce if valid. Returns True if accepted."""
        async with self._lock:
            self._prune()
            nonce_state = self._nonces.pop(nonce, None)
            if nonce_state is None:
                return False
            issued_at, _client_id = nonce_state
            return (time.monotonic() - issued_at) < self._ttl

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [n for n, (t, _c) in self._nonces.items() if (now - t) >= self._ttl]
        for n in expired:
            del self._nonces[n]

    def _evict_client_over_limit(self, client_id: str) -> None:
        per_client_limit = max(1, min(MAX_OUTSTANDING_NONCES_PER_CLIENT, self._max_outstanding))
        client_nonces = [
            (nonce, issued_at)
            for nonce, (issued_at, nonce_client_id) in self._nonces.items()
            if nonce_client_id == client_id
        ]
        client_nonces.sort(key=lambda item: item[1])
        while len(client_nonces) >= per_client_limit:
            nonce, _issued_at = client_nonces.pop(0)
            del self._nonces[nonce]

    def _evict_over_limit(self) -> None:
        while len(self._nonces) >= self._max_outstanding:
            oldest = min(self._nonces, key=lambda nonce: self._nonces[nonce][0])
            del self._nonces[oldest]


class SignerState:
    """Tracks whether the app has ever observed configured admin signers.

    Access is protected by an asyncio.Lock to remain safe if the server
    ever moves to a multi-task or multi-worker topology.
    """

    def __init__(self, initialized: bool = False):
        self._initialized = initialized
        self._lock = asyncio.Lock()

    @property
    def initialized(self) -> bool:
        return self._initialized

    async def mark_initialized(self) -> None:
        async with self._lock:
            self._initialized = True

    async def check_initialized(self) -> bool:
        async with self._lock:
            return self._initialized


# --- Signature Helpers ---


def reapply_signature_message(nonce: str, path: str, payload: bytes) -> str:
    """Build the message string that the client must sign."""
    digest = hashlib.sha256(payload).hexdigest()
    return f"atomixos-reapply-v1\nnonce:{nonce}\npath:{path}\nsha256:{digest}\n"


def verify_ssh_signature(message: str, signature_blob: bytes, allowed_keys_path: Path) -> bool:
    """Verify an SSH signature over a request-bound message.

    The allowed_keys_path should be a file in ssh allowed_signers format.
    Returns True if verification succeeds.
    """
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".sig", delete=False) as sig_file:
        sig_file.write(signature_blob)
        sig_path = sig_file.name

    try:
        result = subprocess.run(
            [
                SSH_KEYGEN_BIN,
                "-Y",
                "verify",
                "-f",
                str(allowed_keys_path),
                "-I",
                "atomixos-reapply",
                "-n",
                "atomixos-reapply",
                "-s",
                sig_path,
            ],
            input=message.encode(),
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    finally:
        Path(sig_path).unlink(missing_ok=True)


def build_allowed_signers(config_root: Path) -> Path | None:
    """Build a temporary allowed_signers file from active admin SSH keys.

    Returns the path to the temp file, or None if no keys exist.
    """
    admin_keys_path = config_root / "admin-signers"
    if not admin_keys_path.exists():
        return None

    keys = [line.strip() for line in admin_keys_path.read_text().splitlines() if line.strip()]
    if not keys:
        return None

    # allowed_signers format: <principal> <key>
    lines = [f"atomixos-reapply {key}" for key in keys]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".allowed_signers", delete=False) as tmp:
        tmp.write("\n".join(lines) + "\n")
        return Path(tmp.name)


# --- Litestar Auth Guard ---


async def _verify_ssh_auth(connection: ASGIConnection, allowed_path: Path) -> None:
    try:
        nonce = connection.headers.get("x-atomixos-nonce", "")
        signature_b64 = connection.headers.get("x-atomixos-signature", "")
        if not nonce or not signature_b64:
            raise NotAuthorizedException(detail=AUTH_REQUIRED_MESSAGE)

        nonce_store: NonceStore = connection.app.state.nonce_store
        if not await nonce_store.consume(nonce):
            raise NotAuthorizedException(detail="invalid or expired nonce")

        body = await connection.body()
        message = reapply_signature_message(nonce, connection.url.path, body)
        try:
            signature_blob = base64.b64decode(signature_b64, validate=True)
        except Exception as exc:
            raise NotAuthorizedException(detail="invalid signature encoding") from exc

        valid = await asyncio.to_thread(
            verify_ssh_signature, message, signature_blob, allowed_path
        )
        if not valid:
            raise NotAuthorizedException(detail="signature verification failed")
        connection.scope["atomixos_authenticated"] = True
    finally:
        Path(allowed_path).unlink(missing_ok=True)


async def ssh_auth_guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    """Guard that enforces SSH signature authentication."""
    config_root: Path = connection.app.state.config_root
    signer_state: SignerState = connection.app.state.signer_state

    # Only a truly unprovisioned root may bypass auth; a provisioned root with
    # missing/corrupt signers must fail closed.
    allowed_path = build_allowed_signers(config_root)
    if allowed_path is None:
        if signer_state.initialized or (config_root / "config.toml").exists():
            raise NotAuthorizedException(detail="admin signers temporarily unavailable")
        return
    await signer_state.mark_initialized()
    await _verify_ssh_auth(connection, allowed_path)


async def ssh_auth_required_guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    """Guard that enforces SSH auth without first-boot bypass."""
    config_root: Path = connection.app.state.config_root
    allowed_path = build_allowed_signers(config_root)
    if allowed_path is None:
        raise NotAuthorizedException(detail=AUTH_REQUIRED_MESSAGE)
    await _verify_ssh_auth(connection, allowed_path)
