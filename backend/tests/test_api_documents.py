"""Tests for document upload and conversation APIs."""

import io
from unittest.mock import patch, MagicMock

from app.models import Document


# ---------------------------------------------------------------------------
# Document upload tests
# ---------------------------------------------------------------------------


def test_upload_document_success(client, tmp_path):
    """Normal upload returns 200 with filename and status."""
    c, mock_db = client
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with (
        patch("app.api.documents.settings") as mock_settings,
        patch("app.api.documents.compute_md5", return_value="fake_md5_hash"),
    ):
        mock_settings.max_upload_size = 10 * 1024 * 1024
        mock_settings.uploads_dir = tmp_path

        response = c.post(
            "/api/documents/upload",
            files={"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")},
            data={"kb_id": 1},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "test.txt"
    assert data["status"] == "pending"


def test_upload_document_unsupported_format(client, tmp_path):
    """Uploading an unsupported file format (.exe) returns 400."""
    c, mock_db = client

    with patch("app.api.documents.settings") as mock_settings:
        mock_settings.max_upload_size = 10 * 1024 * 1024
        mock_settings.uploads_dir = tmp_path

        response = c.post(
            "/api/documents/upload",
            files={"file": ("malware.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")},
            data={"kb_id": 1},
        )

    assert response.status_code == 400
    assert "不支持的文件格式" in response.json()["detail"]


def test_upload_document_duplicate(client, tmp_path):
    """Uploading a duplicate document returns 409."""
    c, mock_db = client

    existing_doc = MagicMock()
    existing_doc.id = 99
    existing_doc.filename = "existing.txt"

    with (
        patch("app.api.documents.settings") as mock_settings,
        patch("app.api.documents.compute_md5", return_value="same_md5_hash"),
    ):
        mock_settings.max_upload_size = 10 * 1024 * 1024
        mock_settings.uploads_dir = tmp_path

        mock_db.query.return_value.filter.return_value.first.return_value = existing_doc

        response = c.post(
            "/api/documents/upload",
            files={"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")},
            data={"kb_id": 1},
        )

    assert response.status_code == 409
    assert "文档已存在" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Conversation API tests
# ---------------------------------------------------------------------------


def test_list_conversations(client):
    """GET /api/chat/history returns 200 with a list."""
    c, mock_db = client
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    response = c.get("/api/chat/history")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_delete_conversation_not_found(client):
    """Deleting a non-existent conversation returns 404."""
    c, mock_db = client
    mock_db.query.return_value.filter.return_value.first.return_value = None

    response = c.delete("/api/chat/99999")

    assert response.status_code == 404
    assert "对话不存在" in response.json()["detail"]
