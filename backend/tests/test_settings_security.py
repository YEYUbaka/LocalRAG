"""Settings security tests: owner-only updates and key hygiene."""

import pytest

TEST_SECRET = "phase-zero-test-secret-with-at-least-32-bytes"


@pytest.fixture
def owner_headers():
    from tests.test_auth_security import _make_token

    return {"Authorization": f"Bearer {_make_token(1)}"}


def test_non_owner_cannot_update_settings(client, monkeypatch):
    from fastapi import HTTPException
    from app.auth import require_owner

    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    c, _ = client

    def _deny_non_owner():
        raise HTTPException(status_code=403, detail="无权限")

    c.app.dependency_overrides[require_owner] = _deny_non_owner
    response = c.put(
        "/api/settings",
        json={"llm_model_name": "blocked"},
    )
    assert response.status_code == 403


def _mock_owner_user():
    from types import SimpleNamespace

    return SimpleNamespace(id=1, username="owner")


def test_settings_owner_response_has_configured_flag(client, monkeypatch):
    from app.auth import require_owner

    monkeypatch.setenv("LLM_API_KEY", "secret-regression-value")
    c, _ = client
    c.app.dependency_overrides[require_owner] = lambda: _mock_owner_user()
    response = c.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert "llm_api_key_configured" in data
    assert data["llm_api_key_configured"] is True
