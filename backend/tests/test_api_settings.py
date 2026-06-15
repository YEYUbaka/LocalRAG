"""Test settings API endpoints."""


def test_get_settings(client):
    c, _ = client
    response = c.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert "llm_base_url" in data
    assert "llm_model_name" in data
    assert "top_k" in data
    assert "temperature" in data
    assert "hybrid_search" in data
    assert "rerank_enabled" in data
    assert "query_rewrite_enabled" in data


def test_update_settings(client):
    c, _ = client
    response = c.put(
        "/api/settings",
        json={"top_k": 10, "temperature": 0.5},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["top_k"] == 10
    assert data["temperature"] == 0.5
