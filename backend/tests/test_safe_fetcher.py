"""SSRF protection tests for SafeFetcher."""

import ipaddress
import socket
from unittest.mock import patch

import pytest

from app.core.safe_fetcher import (
    FetchError,
    FetchErrorCode,
    PublicHttpUrl,
    SafeFetcher,
)

# ---------------------------------------------------------------------------
# PublicHttpUrl.parse rejection cases
# ---------------------------------------------------------------------------

PRIVATE_HOSTNAMES = [
    "http://localhost",
    "http://127.0.0.1",
    "http://0.0.0.0",
    "http://[::1]",
    "http://10.0.0.5",
    "http://172.16.0.5",
    "http://192.168.1.10",
    "http://169.254.169.254",
    "http://224.0.0.1",
    "http://255.255.255.255",
    "http://127.0.0.1/v1",
]


@pytest.mark.parametrize("value", PRIVATE_HOSTNAMES)
def test_private_loopback_and_reserved_addresses_rejected(value):
    with pytest.raises(FetchError) as caught:
        PublicHttpUrl.parse(value)
    assert caught.value.code in (FetchErrorCode.BLOCKED_ADDRESS, FetchErrorCode.INVALID_URL)


@pytest.mark.parametrize("value", [
    "http://2130706433",           # 127.0.0.1 decimal
    "http://0x7f000001",           # 127.0.0.1 hex
    "http://0177.0.0.1",           # 127.0.0.1 octal
    "http://user@example.com",     # userinfo
    "http://example.com/#frag",    # fragment
    "ftp://example.com",           # non-http scheme
    "http://example.com:8080",     # non-standard port
])
def test_alternate_ip_spellings_and_invalid_components_rejected(value):
    with pytest.raises(FetchError):
        PublicHttpUrl.parse(value)


def test_public_url_parses_and_normalizes():
    with patch.object(socket, "getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]):
        url = PublicHttpUrl.parse("HTTPS://EXAMPLE.com:443/path")
    assert url.host == "example.com"
    assert url.addresses == ("93.184.216.34",)
    assert url.url.startswith("https://example.com/path")


def test_hostname_without_public_address_rejected():
    with patch.object(socket, "getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]):
        with pytest.raises(FetchError) as caught:
            PublicHttpUrl.parse("http://example.com")
    assert caught.value.code == FetchErrorCode.BLOCKED_ADDRESS


# ---------------------------------------------------------------------------
# SafeFetcher fetch behavior
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status=200, headers=None, body=b"<html><body>ok</body></html>"):
        self.status = status
        self.headers = headers or {"content-type": "text/html"}
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def aiter_bytes(self):
        async def _gen():
            yield self.body
        return _gen()


class _FakeStreamClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.follow_redirects = False
        self.trust_env = False

    def stream(self, method, url, **kwargs):
        return self._responses.pop(0)

    async def aclose(self):
        return None


def _public_url(host="example.com"):
    with patch.object(socket, "getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]):
        return PublicHttpUrl.parse(f"http://{host}/")


@pytest.mark.asyncio
async def test_fetch_returns_html_for_public_url():
    fetcher = SafeFetcher()
    fetcher._client = _FakeStreamClient([_FakeResponse()])
    result = await fetcher.fetch(_public_url())
    assert "ok" in result.html
    await fetcher.aclose()


@pytest.mark.asyncio
async def test_redirect_chain_revalidates_each_hop():
    # Redirect to private address must be blocked
    redirect_resp = _FakeResponse(
        status=302,
        headers={"content-type": "text/html", "location": "http://127.0.0.1/private"},
    )
    fetcher = SafeFetcher()
    fetcher._client = _FakeStreamClient([redirect_resp])

    # IP literal hosts resolve via getaddrinfo -> return loopback so parse blocks
    # Direct construction bypasses DNS, so the FIRST getaddrinfo call is the redirect parse
    with patch.object(socket, "getaddrinfo", side_effect=[
        [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))],      # redirect -> blocked
    ]):
        with pytest.raises(FetchError) as caught:
            await fetcher.fetch(PublicHttpUrl(url="http://example.com/", host="example.com", addresses=("93.184.216.34",)))
    assert caught.value.code == FetchErrorCode.BLOCKED_ADDRESS
    await fetcher.aclose()


@pytest.mark.asyncio
async def test_six_hop_redirect_chain_rejected():
    chain = [
        _FakeResponse(status=302, headers={"content-type": "text/html", "location": f"http://example.com/step{i+1}"})
        for i in range(6)
    ]
    fetcher = SafeFetcher()
    fetcher._client = _FakeStreamClient(chain)

    with patch.object(socket, "getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]):
        with pytest.raises(FetchError) as caught:
            await fetcher.fetch(_public_url())
    assert caught.value.code == FetchErrorCode.REDIRECT_LIMIT
    await fetcher.aclose()


@pytest.mark.asyncio
async def test_oversized_response_rejected():
    big = b"<html><body>" + b"x" * (2 * 1024 * 1024 + 10) + b"</body></html>"
    fetcher = SafeFetcher()
    fetcher._client = _FakeStreamClient([_FakeResponse(body=big)])
    with pytest.raises(FetchError) as caught:
        await fetcher.fetch(_public_url())
    assert caught.value.code == FetchErrorCode.RESPONSE_TOO_LARGE
    await fetcher.aclose()


@pytest.mark.asyncio
async def test_non_html_media_type_rejected():
    fetcher = SafeFetcher()
    fetcher._client = _FakeStreamClient([
        _FakeResponse(status=200, headers={"content-type": "application/pdf"})
    ])
    with pytest.raises(FetchError) as caught:
        await fetcher.fetch(_public_url())
    assert caught.value.code == FetchErrorCode.UNSUPPORTED_MEDIA_TYPE
    await fetcher.aclose()
