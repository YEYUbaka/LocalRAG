"""Test knowledge base API endpoints."""

from unittest.mock import MagicMock


def test_list_kbs(client):
    c, mock_session = client
    mock_kb = MagicMock()
    mock_kb.id = 1
    mock_kb.name = "默认知识库"
    mock_kb.description = "系统默认知识库"
    mock_kb.created_at = None

    # query(KnowledgeBase).filter().order_by().all() → [mock_kb]
    # query(Document).filter().count() → 0
    def mock_query(model):
        q = MagicMock()
        if hasattr(model, '__tablename__') and model.__tablename__ == 'knowledge_bases':
            q.filter.return_value.order_by.return_value.all.return_value = [mock_kb]
        else:
            q.filter.return_value.count.return_value = 0
        return q

    mock_session.query.side_effect = mock_query

    response = c.get("/api/kb")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["name"] == "默认知识库"


def test_create_kb(client):
    c, mock_session = client
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()

    def set_id(obj):
        obj.id = 2

    mock_session.refresh.side_effect = set_id

    response = c.post("/api/kb", json={"name": "测试知识库", "description": "测试"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "测试知识库"
    assert data["description"] == "测试"
