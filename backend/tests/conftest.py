"""Test fixtures for LocalRAG backend tests."""

import pytest
from unittest.mock import MagicMock, patch


# Patch module-level DB initialization BEFORE importing app.main
_mock_session_local = MagicMock()


def _mock_get_db():
    """Generic mock get_db that yields the shared mock session."""
    try:
        yield _mock_session_local
    finally:
        pass


# Mock user for auth
_mock_user = MagicMock()
_mock_user.id = 1
_mock_user.username = "testuser"


def _mock_get_current_user():
    return _mock_user


with (
    patch("sqlalchemy.create_engine") as mock_engine,
    patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker,
    patch.object(
        __import__("app.models", fromlist=["Base"]).Base.metadata,
        "create_all",
    ),
):
    mock_sessionmaker.return_value = _mock_session_local
    from app.main import app
    from app.api.documents import get_db
    from app.api.chat import get_db as chat_get_db
    from app.api.knowledge_bases import get_db as kb_get_db
    from app.api.export import get_db as export_get_db
    from app.api.tags import get_db as tags_get_db
    from app.auth import get_current_user


@pytest.fixture
def client():
    """Create a test client with mocked DB session and auth."""
    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[chat_get_db] = _mock_get_db
    app.dependency_overrides[kb_get_db] = _mock_get_db
    app.dependency_overrides[export_get_db] = _mock_get_db
    app.dependency_overrides[tags_get_db] = _mock_get_db
    app.dependency_overrides[get_current_user] = _mock_get_current_user

    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c, _mock_session_local

    app.dependency_overrides.clear()
