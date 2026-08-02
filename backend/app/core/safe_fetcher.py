"""Safe HTTP fetch with SSRF protection.

Every URL passed to the network layer must be a validated ``PublicHttpUrl``
whose resolved addresses are all public. Redirects are re-validated as fresh
URLs; responses are bounded in size; only HTML media types are accepted.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urljoin, urlparse

import httpx

MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MiB
TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0)
ALLOWED_MEDIA_TYPES = {"text/html", "application/xhtml+xml"}
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


class FetchErrorCode(StrEnum):
    INVALID_URL = "invalid_url"
    BLOCKED_ADDRESS = "blocked_address"
    REDIRECT_LIMIT = "redirect_limit"
    RESPONSE_TOO_LARGE = "response_too_large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    TIMEOUT = "timeout"
    UPSTREAM_ERROR = "upstream_error"


@dataclass(frozen=True)
class FetchError(Exception):
    code: FetchErrorCode

    def __str__(self) -> str:
        return self.code.value


@dataclass(frozen=True)
class FetchResult:
    url: str
    html: str
    final_url: str


def _is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        address.is_global
        and not any((
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        ))
    )


@dataclass(frozen=True, slots=True)
class PublicHttpUrl:
    url: str
    host: str
    addresses: tuple[str, ...]

    @classmethod
    def parse(cls, value: str) -> "PublicHttpUrl":
        try:
            parsed = urlparse(value)
        except ValueError:
            raise FetchError(FetchErrorCode.INVALID_URL)
        if parsed.scheme.lower() not in ("http", "https"):
            raise FetchError(FetchErrorCode.INVALID_URL)
        if parsed.username or parsed.password:
            raise FetchError(FetchErrorCode.INVALID_URL)
        if parsed.fragment:
            raise FetchError(FetchErrorCode.INVALID_URL)
        if not parsed.hostname:
            raise FetchError(FetchErrorCode.INVALID_URL)
        port = parsed.port
        if port is not None and port not in (80, 443):
            raise FetchError(FetchErrorCode.INVALID_URL)

        host = parsed.hostname
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror:
            raise FetchError(FetchErrorCode.INVALID_URL)

        addresses: list[str] = []
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if not _is_public(ip):
                raise FetchError(FetchErrorCode.BLOCKED_ADDRESS)
            addresses.append(str(ip))
        if not addresses:
            raise FetchError(FetchErrorCode.BLOCKED_ADDRESS)

        # Normalize: lowercase scheme/host, drop default port, strip fragment
        scheme = parsed.scheme.lower()
        hostname_norm = host
        port_norm = parsed.port
        netloc = hostname_norm if port_norm in (None, 80, 443) else f"{hostname_norm}:{port_norm}"
        path = parsed.path or "/"
        query = f"?{parsed.query}" if parsed.query else ""
        normalized = urljoin(f"{scheme}://{netloc}", path + query)
        return cls(url=normalized, host=hostname_norm, addresses=tuple(dict.fromkeys(addresses)))


class SafeFetcher:
    """Bounded, redirect-validating HTTP fetcher for public HTML only."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=TIMEOUT,
            follow_redirects=False,
            trust_env=False,
        )

    async def fetch(self, url: PublicHttpUrl) -> FetchResult:
        current = url
        for _hop in range(MAX_REDIRECTS + 1):
            result = await self._fetch_once(current)
            if result.status in (301, 302, 303, 307, 308):
                location = result.headers.get("location")
                if not location:
                    raise FetchError(FetchErrorCode.UPSTREAM_ERROR)
                try:
                    next_url = urljoin(current.url, location)
                    current = PublicHttpUrl.parse(next_url)
                except FetchError:
                    raise
                continue
            if result.status >= 400:
                raise FetchError(FetchErrorCode.UPSTREAM_ERROR)

            media_type = result.headers.get("content-type", "").split(";")[0].strip().lower()
            if media_type not in ALLOWED_MEDIA_TYPES:
                raise FetchError(FetchErrorCode.UNSUPPORTED_MEDIA_TYPE)
            return FetchResult(url=current.url, html=result.body.decode("utf-8", errors="replace"), final_url=current.url)

        raise FetchError(FetchErrorCode.REDIRECT_LIMIT)

    async def _fetch_once(self, url: PublicHttpUrl) -> httpx.Response:
        try:
            async with self._client.stream("GET", url.url) as resp:
                chunks: list[bytes] = []
                size = 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise FetchError(FetchErrorCode.RESPONSE_TOO_LARGE)
                    chunks.append(chunk)
                resp._content = b"".join(chunks)
                return resp
        except FetchError:
            raise
        except httpx.TimeoutException:
            raise FetchError(FetchErrorCode.TIMEOUT)
        except httpx.HTTPError:
            raise FetchError(FetchErrorCode.UPSTREAM_ERROR)

    async def aclose(self) -> None:
        await self._client.aclose()
