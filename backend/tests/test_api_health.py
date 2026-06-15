"""Test health endpoint."""


def test_health(client):
    c, _ = client
    response = c.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
