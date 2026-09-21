"""Tests for image understanding and deep thinking RAG query modes."""

import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _parse_sse_events(raw: str) -> list[tuple[str, dict]]:
    """Parse SSE text into list of (event_type, data_dict)."""
    events = []
    for block in raw.strip().split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_type = ""
        data_str = ""
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[len("event: "):]
            elif line.startswith("data: "):
                data_str = line[len("data: "):]
        if event_type and data_str:
            events.append((event_type, json.loads(data_str)))
    return events


def _make_mock_chunk(text: str) -> MagicMock:
    """Create a mock LLM streaming chunk."""
    chunk = MagicMock()
    chunk.content = text
    return chunk


async def _async_iter(items):
    """Turn a list into an async iterator."""
    for item in items:
        yield item


# ── rag_query_with_image ──────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.rag_service.get_conversation_history", return_value=[])
@patch("app.services.rag_service.hybrid_search", return_value=[])
@patch("app.services.llm_service.get_vision_model")
async def test_rag_query_with_image_emits_events(
    mock_get_vision_model, mock_hybrid_search, mock_get_history
):
    """Verify that rag_query_with_image emits token and done SSE events."""
    from app.services.rag_service import rag_query_with_image

    # Arrange: mock vision model that streams back two chunks
    # astream must return an async iterable (not a coroutine), so use MagicMock
    mock_model = MagicMock()
    mock_model.astream = MagicMock(
        return_value=_async_iter([_make_mock_chunk("图片"), _make_mock_chunk("分析结果")])
    )
    mock_get_vision_model.return_value = mock_model

    mock_db = MagicMock()
    mock_conversation = MagicMock()
    mock_conversation.id = 42
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.refresh = MagicMock(
        side_effect=lambda obj: setattr(obj, "id", 42) if not hasattr(obj, "id") or obj.id is None else None
    )

    # Patch Conversation so that db.add sets an id
    with patch("app.services.rag_service.Conversation") as MockConv, \
         patch("app.services.rag_service.Message") as MockMsg:
        conv_instance = MagicMock()
        conv_instance.id = 42
        MockConv.return_value = conv_instance

        # Act
        raw_events = ""
        async for event in rag_query_with_image(
            question="描述这张图片",
            image_base64="data:image/png;base64,abc123",
            conversation_id=None,
            db=mock_db,
            scope=None,
            user_id=1,
        ):
            raw_events += event

    # Assert: parse and check event types
    events = _parse_sse_events(raw_events)
    event_types = [e[0] for e in events]

    assert "token" in event_types, f"Expected 'token' event, got: {event_types}"
    assert "done" in event_types, f"Expected 'done' event, got: {event_types}"

    # Verify token content
    token_events = [e for e in events if e[0] == "token"]
    full_text = "".join(e[1]["content"] for e in token_events)
    assert "图片" in full_text
    assert "分析结果" in full_text

    # Verify done event carries conversation_id
    done_events = [e for e in events if e[0] == "done"]
    assert done_events[0][1]["conversation_id"] == 42


@pytest.mark.asyncio
async def test_rag_query_with_image_uses_unified_search_when_enabled(monkeypatch):
    from app.domain.tenant import TenantScope
    from app.services.rag_service import rag_query_with_image

    unified_calls = []
    mock_model = MagicMock()
    mock_model.astream = MagicMock(return_value=_async_iter([_make_mock_chunk("完成")]))
    monkeypatch.setattr("app.services.llm_service.get_vision_model", lambda: mock_model)
    monkeypatch.setattr("app.services.rag_service.settings.unified_fusion_enabled", True)
    monkeypatch.setattr(
        "app.services.rag_service.unified_search",
        lambda scope, original, queries: unified_calls.append((scope, original, queries)) or [],
    )
    monkeypatch.setattr(
        "app.services.rag_service.hybrid_search",
        lambda *args: pytest.fail("flag-on 图片路径不应调用 legacy hybrid_search"),
    )
    scope = TenantScope(7, 11)
    mock_db = MagicMock()

    with patch("app.services.rag_service.Conversation") as mock_conversation, patch(
        "app.services.rag_service.Message"
    ):
        mock_conversation.return_value.id = 42
        async for _ in rag_query_with_image(
            question="原问题",
            image_base64="data:image/png;base64,abc123",
            conversation_id=None,
            db=mock_db,
            scope=scope,
            user_id=7,
        ):
            pass

    assert unified_calls == [(scope, "原问题", ["原问题"])]


# ── rag_query_with_thinking ───────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.services.rag_service._try_web_search", new_callable=AsyncMock)
@patch("app.services.rag_service.get_conversation_history", return_value=[])
@patch("app.services.rag_service.hybrid_search", return_value=[])
@patch("app.services.rag_service.get_thinking_model")
@patch("app.services.rag_service.settings")
async def test_rag_query_with_thinking_emits_thinking_event(
    mock_settings,
    mock_get_thinking_model,
    mock_hybrid_search,
    mock_get_history,
    mock_web_search,
):
    """Verify that rag_query_with_thinking emits thinking, token, and done events."""
    from app.services.rag_service import rag_query_with_thinking

    # Arrange: configure settings
    mock_settings.query_rewrite_enabled = False
    mock_settings.unified_fusion_enabled = False
    mock_settings.context_window = 8192
    mock_settings.web_search_enabled = False
    mock_settings.rerank_enabled = False

    # web_search passthrough (returns sources unchanged)
    mock_web_search.side_effect = lambda q, sources, kb_id: sources

    # Mock thinking model that streams back content
    # astream must return an async iterable (not a coroutine), so use MagicMock
    mock_model = MagicMock()
    mock_model.astream = MagicMock(
        return_value=_async_iter([_make_mock_chunk("深度"), _make_mock_chunk("思考结果")])
    )
    mock_get_thinking_model.return_value = mock_model

    mock_db = MagicMock()

    with patch("app.services.rag_service.Conversation") as MockConv, \
         patch("app.services.rag_service.Message") as MockMsg:
        conv_instance = MagicMock()
        conv_instance.id = 99
        MockConv.return_value = conv_instance

        # Act
        raw_events = ""
        async for event in rag_query_with_thinking(
            question="请深度思考这个问题",
            conversation_id=None,
            db=mock_db,
            scope=None,
            user_id=1,
        ):
            raw_events += event

    # Assert
    events = _parse_sse_events(raw_events)
    event_types = [e[0] for e in events]

    assert "thinking" in event_types, f"Expected 'thinking' event, got: {event_types}"
    assert "token" in event_types, f"Expected 'token' event, got: {event_types}"
    assert "done" in event_types, f"Expected 'done' event, got: {event_types}"

    # Verify thinking event has started status
    thinking_events = [e for e in events if e[0] == "thinking"]
    thinking_statuses = [e[1]["status"] for e in thinking_events]
    assert "started" in thinking_statuses, f"Expected 'started' thinking status, got: {thinking_statuses}"

    # Verify token content
    token_events = [e for e in events if e[0] == "token"]
    full_text = "".join(e[1]["content"] for e in token_events)
    assert "深度" in full_text
    assert "思考结果" in full_text

    # Verify done event carries conversation_id
    done_events = [e for e in events if e[0] == "done"]
    assert done_events[0][1]["conversation_id"] == 99
