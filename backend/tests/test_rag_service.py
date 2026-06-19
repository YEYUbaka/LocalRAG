"""Tests for app.services.rag_service module."""

import pytest
from unittest.mock import MagicMock, patch

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.services.rag_service import (
    estimate_tokens,
    build_messages,
    get_conversation_history,
    MAX_HISTORY_ROUNDS,
)


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    """estimate_tokens: chinese_chars//2 + other_chars//4 + 1"""

    def test_empty_string(self):
        assert estimate_tokens("") == 1

    def test_pure_chinese(self):
        # 4 个中文字符 => 4//2 + 0//4 + 1 = 3
        assert estimate_tokens("你好世界") == 3

    def test_pure_english(self):
        # 5 个英文字符 => 0//2 + 5//4 + 1 = 2
        assert estimate_tokens("hello") == 2

    def test_mixed_chinese_english(self):
        # "你好hello" => 2 中文 + 5 英文 => 2//2 + 5//4 + 1 = 1 + 1 + 1 = 3
        assert estimate_tokens("你好hello") == 3

    def test_long_chinese_text(self):
        # 13 个中文字符 => 13//2 + 0//4 + 1 = 7
        text = "这是一段较长的中文文本内容"
        assert estimate_tokens(text) == 7

    def test_long_english_text(self):
        # 39 个非中文字符(20字母+19标点) => 0//2 + 39//4 + 1 = 10
        text = "a]b]c]d]e]f]g]h]i]j]k]l]m]n]o]p]q]r]s]t"
        assert estimate_tokens(text) == 10

    def test_numbers_and_punctuation(self):
        # "12345!@#" => 8 个非中文字符 => 0//2 + 8//4 + 1 = 3
        assert estimate_tokens("12345!@#") == 3

    def test_single_chinese_char(self):
        # 1 中文 => 1//2 + 0//4 + 1 = 1
        assert estimate_tokens("好") == 1

    def test_single_english_char(self):
        # 1 英文 => 0//2 + 1//4 + 1 = 1
        assert estimate_tokens("a") == 1


# ---------------------------------------------------------------------------
# build_messages
# ---------------------------------------------------------------------------


class TestBuildMessages:
    """build_messages returns list[BaseMessage]: SystemMessage + history + HumanMessage."""

    @patch("app.services.rag_service.build_rag_prompt")
    def test_no_sources_no_history(self, mock_prompt):
        mock_prompt.return_value = "你是测试助手"
        result = build_messages("什么是 Python？", [], [])

        assert len(result) == 2
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "你是测试助手"
        assert isinstance(result[1], HumanMessage)
        assert result[1].content == "什么是 Python？"

    @patch("app.services.rag_service.build_rag_prompt")
    def test_with_sources(self, mock_prompt):
        mock_prompt.return_value = "系统提示（含来源）"
        sources = [{"document": "Python 是一种编程语言", "metadata": {}}]

        result = build_messages("什么是 Python？", sources, [])

        assert len(result) == 2
        assert isinstance(result[0], SystemMessage)
        mock_prompt.assert_called_once_with("什么是 Python？", sources)

    @patch("app.services.rag_service.build_rag_prompt")
    def test_with_history(self, mock_prompt):
        mock_prompt.return_value = "系统提示"
        history = [
            MagicMock(role="user", content="你好"),
            MagicMock(role="assistant", content="你好！有什么可以帮你？"),
        ]

        result = build_messages("什么是 Python？", [], history)

        # system + 2 history + human = 4
        assert len(result) == 4
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[1], HumanMessage)
        assert result[1].content == "你好"
        assert isinstance(result[2], AIMessage)
        assert result[2].content == "你好！有什么可以帮你？"
        assert isinstance(result[3], HumanMessage)
        assert result[3].content == "什么是 Python？"

    @patch("app.services.rag_service.build_rag_prompt")
    def test_with_sources_and_history(self, mock_prompt):
        mock_prompt.return_value = "系统提示"
        sources = [{"document": "片段内容", "metadata": {}}]
        history = [
            MagicMock(role="user", content="问题一"),
            MagicMock(role="assistant", content="回答一"),
            MagicMock(role="user", content="问题二"),
            MagicMock(role="assistant", content="回答二"),
        ]

        result = build_messages("新问题", sources, history)

        # system + 4 history + human = 6
        assert len(result) == 6
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[-1], HumanMessage)
        assert result[-1].content == "新问题"
        # 验证 build_rag_prompt 收到了 sources
        mock_prompt.assert_called_once_with("新问题", sources)

    @patch("app.services.rag_service.build_rag_prompt")
    def test_first_is_system_last_is_human(self, mock_prompt):
        """通用断言：第一条永远是 SystemMessage，最后一条永远是 HumanMessage。"""
        mock_prompt.return_value = "prompt"
        history = [MagicMock(role="user", content="q1"), MagicMock(role="assistant", content="a1")]

        result = build_messages("最终问题", [], history)

        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[-1], HumanMessage)
        assert result[-1].content == "最终问题"


# ---------------------------------------------------------------------------
# get_conversation_history
# ---------------------------------------------------------------------------


class TestGetConversationHistory:
    """get_conversation_history: 按 MAX_HISTORY_ROUNDS 截断 + token 预算截断。"""

    def _make_messages(self, n):
        """创建 n 条交替的 user/assistant 消息（从 assistant 开始）。"""
        msgs = []
        for i in range(n):
            m = MagicMock()
            m.role = "user" if i % 2 == 0 else "assistant"
            # 每条约 10 个英文字符 => estimate_tokens ≈ 10//4+1 = 3
            m.content = f"message {i}"
            m.created_at = MagicMock()
            msgs.append(m)
        return msgs

    def test_returns_all_when_no_token_limit_and_within_rounds(self):
        """消息数 <= MAX_HISTORY_ROUNDS*2 且无 token 限制时，全部返回。"""
        all_msgs = self._make_messages(6)  # 3 轮
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = all_msgs

        result = get_conversation_history(db, conversation_id=1)

        assert len(result) == 6

    def test_truncates_to_max_history_rounds(self):
        """消息数超过 MAX_HISTORY_ROUNDS*2 时，只保留最近 N*2 条。"""
        all_msgs = self._make_messages(20)  # 10 轮，超过默认 5 轮
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = all_msgs

        result = get_conversation_history(db, conversation_id=1)

        expected = MAX_HISTORY_ROUNDS * 2  # 10
        assert len(result) == expected
        # 验证保留的是最后 10 条
        assert result[0] is all_msgs[-expected]

    def test_token_budget_truncation(self):
        """设置 max_tokens 后，应按 token 预算截断历史。"""
        all_msgs = self._make_messages(6)
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = all_msgs

        # 每条消息约 3 tokens，限制只允许 7 tokens => 最多容纳 2 条
        result = get_conversation_history(db, conversation_id=1, max_tokens=7)

        assert len(result) <= 3  # 至少不会超过预算
        # 验证总 token 不超预算
        total = sum(estimate_tokens(m.content) for m in result)
        assert total <= 7

    def test_token_budget_very_small(self):
        """token 预算极小时返回空列表。"""
        all_msgs = self._make_messages(4)
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = all_msgs

        # max_tokens=0，任何消息都无法放入
        result = get_conversation_history(db, conversation_id=1, max_tokens=0)

        assert result == []

    def test_no_token_limit_returns_last_n_rounds(self):
        """max_tokens=None 时，只受 MAX_HISTORY_ROUNDS 限制。"""
        all_msgs = self._make_messages(30)
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = all_msgs

        result = get_conversation_history(db, conversation_id=1, max_tokens=None)

        assert len(result) == MAX_HISTORY_ROUNDS * 2

    def test_empty_history(self):
        """没有历史消息时返回空列表。"""
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        result = get_conversation_history(db, conversation_id=1, max_tokens=100)

        assert result == []

    def test_preserves_order_after_truncation(self):
        """token 截断后消息顺序仍然从旧到新。"""
        all_msgs = self._make_messages(6)
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = all_msgs

        result = get_conversation_history(db, conversation_id=1, max_tokens=20)

        # 结果顺序应与原始顺序一致
        for i in range(len(result) - 1):
            assert result[i] is all_msgs[all_msgs.index(result[i])]
            assert all_msgs.index(result[i]) < all_msgs.index(result[i + 1])


# ---------------------------------------------------------------------------
# MAX_HISTORY_ROUNDS 常量
# ---------------------------------------------------------------------------


class TestConstants:
    def test_max_history_rounds_default(self):
        assert MAX_HISTORY_ROUNDS == 5
