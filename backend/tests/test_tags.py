"""Test tag API endpoints."""

from unittest.mock import MagicMock


def _reset_mock(mock_db):
    """Reset shared mock state left by other test modules."""
    mock_db.reset_mock(side_effect=True, return_value=True)


def test_create_tag(client):
    """创建标签应返回 200"""
    c, mock_db = client
    _reset_mock(mock_db)
    mock_db.query.return_value.filter.return_value.first.return_value = None

    # mock refresh to simulate DB assigning an id
    def mock_refresh(obj):
        obj.id = 1

    mock_db.refresh.side_effect = mock_refresh

    response = c.post("/api/tags", json={"name": "面试", "color": "blue"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "面试"
    assert data["color"] == "blue"


def test_create_tag_duplicate(client):
    """创建重复标签应返回 409"""
    c, mock_db = client
    _reset_mock(mock_db)
    existing = MagicMock()
    existing.name = "面试"
    mock_db.query.return_value.filter.return_value.first.return_value = existing

    response = c.post("/api/tags", json={"name": "面试"})
    assert response.status_code == 409


def test_list_tags(client):
    """获取标签列表应返回 200"""
    c, mock_db = client
    _reset_mock(mock_db)
    mock_db.query.return_value.all.return_value = []

    response = c.get("/api/tags")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_delete_tag_not_found(client):
    """删除不存在的标签应返回 404"""
    c, mock_db = client
    _reset_mock(mock_db)
    mock_db.query.return_value.filter.return_value.first.return_value = None

    response = c.delete("/api/tags/999")
    assert response.status_code == 404


def test_attach_tag(client):
    """为文档添加标签应返回 200"""
    c, mock_db = client
    _reset_mock(mock_db)
    mock_doc = MagicMock()
    mock_tag = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [mock_doc, mock_tag, None]

    response = c.post("/api/tags/attach?document_id=1&tag_id=1")
    assert response.status_code == 200


def test_detach_tag_not_found(client):
    """移除不存在的关联应返回 404"""
    c, mock_db = client
    _reset_mock(mock_db)
    mock_db.query.return_value.filter.return_value.first.return_value = None

    response = c.post("/api/tags/detach?document_id=1&tag_id=999")
    assert response.status_code == 404
