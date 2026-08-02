"""Security regression tests for owner authentication and secrets."""

import pytest
from fastapi import HTTPException
from jose import jwt as jose_jwt

from app.security.secrets import (
    EnvironmentSecretProvider,
    build_auth_config,
)

TEST_SECRET = "phase-zero-test-secret-with-at-least-32-bytes"


def _make_token(sub: int, **overrides) -> str:
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    claims = {
        "sub": str(sub),
        "iss": "localrag",
        "aud": "localrag-api",
        "iat": now,
        "nbf": now,
        "exp": now + datetime.timedelta(minutes=15),
        "type": "access",
    }
    claims.update(overrides)
    return jose_jwt.encode(claims, TEST_SECRET, algorithm="HS256")


def test_default_or_missing_jwt_secret_fails_startup(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        build_auth_config(EnvironmentSecretProvider())


@pytest.mark.parametrize("claims", [
    {"iss": "wrong", "aud": "localrag-api", "type": "access"},
    {"iss": "localrag", "aud": "wrong", "type": "access"},
    {"iss": "localrag", "aud": "localrag-api", "type": "refresh"},
])
def test_token_rejects_wrong_issuer_audience_and_type(monkeypatch, claims):
    from app.auth import decode_token

    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    token = _make_token(1, **claims)
    with pytest.raises(HTTPException) as caught:
        decode_token(token)
    assert caught.value.status_code == 401


def test_settings_requires_authentication(client):
    from fastapi.testclient import TestClient
    from app.main import app as main_app
    from app.api.documents import get_db

    c, _ = client
    main_app.dependency_overrides.clear()
    main_app.dependency_overrides[get_db] = lambda: iter([_MockSession()])

    with TestClient(main_app) as anon:
        assert anon.get("/api/settings").status_code in (401, 403)
        assert anon.put("/api/settings", json={}).status_code in (401, 403)


class _MockSession:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_settings_never_returns_api_key(client, monkeypatch):
    from app.auth import get_current_user, require_owner

    monkeypatch.setenv("LLM_API_KEY", "secret-regression-value")
    c, _ = client
    c.app.dependency_overrides[require_owner] = lambda: _mock_owner_user()
    response = c.get("/api/settings")
    assert response.status_code == 200
    assert "secret-regression-value" not in response.text


def _mock_owner_user():
    from types import SimpleNamespace

    return SimpleNamespace(id=1, username="owner")


def test_llm_base_url_rejects_http_ip_literal_and_userinfo(client):
    from app.auth import require_owner

    c, _ = client
    c.app.dependency_overrides[require_owner] = lambda: _mock_owner_user()
    for value in [
        "http://api.example.com/v1",
        "https://127.0.0.1/v1",
        "https://user@api.example.com/v1",
    ]:
        response = c.put("/api/settings", json={"llm_base_url": value})
        assert response.status_code == 422, value
