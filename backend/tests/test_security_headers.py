"""Security headers tests: front door must send hardening headers."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_nginx_sends_security_headers():
    nginx_conf = REPO_ROOT / "frontend" / "nginx.conf"
    assert nginx_conf.exists()
    text = nginx_conf.read_text(encoding="utf-8")
    assert "X-Content-Type-Options" in text and "nosniff" in text
    assert "Referrer-Policy" in text and "no-referrer" in text
    assert "X-Frame-Options" in text and "DENY" in text
    assert "Content-Security-Policy" in text
    assert "unsafe-eval" not in text


def test_backend_errors_do_not_leak_stack_traces():
    from app.main import app

    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/nonexistent-endpoint-xyz")
        assert response.status_code == 404
        assert "Traceback" not in response.text
        assert "app\\" not in response.text
