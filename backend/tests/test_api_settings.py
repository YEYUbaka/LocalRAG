"""Test settings API endpoints."""

import pytest


@pytest.fixture
def owner_client(client):
    """Client with the require_owner dependency overridden to allow access."""
    from app.auth import require_owner

    c, _ = client
    from types import SimpleNamespace

    c.app.dependency_overrides[require_owner] = lambda: SimpleNamespace(id=1, username="owner")
    yield c
    c.app.dependency_overrides.pop(require_owner, None)


def test_get_settings(owner_client):
    response = owner_client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert "llm_base_url" in data
    assert "llm_model_name" in data
    assert "top_k" in data
    assert "temperature" in data
    assert "hybrid_search" in data
    assert "rerank_enabled" in data
    assert "query_rewrite_enabled" in data


def test_update_settings(owner_client):
    response = owner_client.put(
        "/api/settings",
        json={"top_k": 10, "temperature": 0.5},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["top_k"] == 10
    assert data["temperature"] == 0.5
