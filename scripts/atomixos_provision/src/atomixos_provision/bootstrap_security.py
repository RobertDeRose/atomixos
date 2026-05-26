"""First-boot browser request checks."""

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse

from litestar import Request
from litestar.exceptions import NotAuthorizedException

__all__ = ["enforce_bootstrap_browser_origin"]


@dataclass(frozen=True)
class RequestOrigin:
    scheme: str
    host: str
    port: int


def _host_name(value: str) -> str:
    if value.startswith("["):
        return value.split("]", 1)[0].strip("[]").lower()
    return value.rsplit(":", 1)[0].lower()


def _allowed_host(hostname: str) -> bool:
    if hostname in {"localhost", "gateway", "atomixos"} or hostname.endswith(".local"):
        return True
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


def _host_origin(host_header: str) -> RequestOrigin | None:
    try:
        parsed = urlparse(f"//{host_header}")
        if not parsed.hostname:
            return None
        return RequestOrigin("http", parsed.hostname.lower(), parsed.port or 80)
    except ValueError:
        return None


def _header_origin(value: str) -> RequestOrigin | None:
    try:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        default_port = 443 if parsed.scheme == "https" else 80
        return RequestOrigin(parsed.scheme, parsed.hostname.lower(), parsed.port or default_port)
    except ValueError:
        return None


def enforce_bootstrap_browser_origin(request: Request) -> None:
    """Reject browser-capable first-boot requests with DNS-rebindable hosts."""
    host_origin = _host_origin(request.headers.get("host", ""))
    if not host_origin or not _allowed_host(host_origin.host):
        raise NotAuthorizedException(detail="bootstrap host is not allowed")

    for header in ("origin", "referer"):
        value = request.headers.get(header, "")
        if not value:
            continue
        header_origin = _header_origin(value)
        if header_origin is None or header_origin != host_origin:
            raise NotAuthorizedException(detail=f"bootstrap {header} is not allowed")
