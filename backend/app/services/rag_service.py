import json
import logging
from collections.abc import AsyncGenerator

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from sqlalchemy.orm import Session

from app.core.vectorstore import hybrid_search
from app.core.prompts import build_rag_prompt
from app.services.llm_service import get_chat_model
from app.config import settings
from app.models import Conversation, Message

logger = logging.getLogger(__name__)


MAX_HISTORY_ROUNDS = 5
# 默认上下文窗口大小（token 数），可通过配置覆盖
DEFAULT_CONTEXT_WINDOW = 8192
# 历史 + 检索片段占上下文窗口的比例
TOKEN_BUDGET_RATIO = 0.6


def estimate_tokens(text: str) -> int:
    """估算 token 数量（中文约 2 字符/token，英文约 4 字符/token）"""
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
    other_chars = len(text) - chinese_chars
    return chinese_chars // 2 + other_chars // 4 + 1


def get_conversation_history(db: Session, conversation_id: int, max_tokens: int | None = None) -> list:
    """获取对话历史，根据 token 预算截断"""
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .all()
    )

    # 先取最近 N 轮
    history = messages[-MAX_HISTORY_ROUNDS * 2:]

    if max_tokens is None:
        return history

    # 从最新到最旧，累加 token 直到超预算
    total_tokens = 0
    truncated = []
    for msg in reversed(history):
        msg_tokens = estimate_tokens(msg.content)
        if total_tokens + msg_tokens > max_tokens:
            break
        truncated.insert(0, msg)
        total_tokens += msg_tokens

    return truncated


def build_messages(question: str, sources: list[dict], history: list) -> list:
    system_prompt = build_rag_prompt(question, sources)

    langchain_messages = [SystemMessage(content=system_prompt)]

    for msg in history:
        if msg.role == "user":
            langchain_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            langchain_messages.append(AIMessage(content=msg.content))

    langchain_messages.append(HumanMessage(content=question))
    return langchain_messages


async def rag_query(
    question: str,
    conversation_id: int | None,
    db: Session,
    kb_id: int | None = None,
    user_id: int | None = None,
) -> AsyncGenerator[str, None]:
    try:
        # Multi-query search: rewrite query and search with each variant
        if settings.query_rewrite_enabled:
            from app.services.query_rewrite import rewrite_query
            queries = await rewrite_query(question)

            all_sources = []
            seen_ids: set[str] = set()
            for q in queries:
                results = hybrid_search(q, kb_id=kb_id)
                for r in results:
                    if r["id"] not in seen_ids:
                        seen_ids.add(r["id"])
                        all_sources.append(r)

            sources = all_sources[:settings.rerank_top_k]
        else:
            sources = hybrid_search(question, kb_id=kb_id)

        # 计算 token 预算
        context_window = getattr(settings, 'context_window', DEFAULT_CONTEXT_WINDOW)
        total_budget = int(context_window * TOKEN_BUDGET_RATIO)

        # 估算检索片段的 token 数
        sources_text = " ".join(s["document"] for s in sources)
        sources_tokens = estimate_tokens(sources_text)

        # 历史消息可用的 token 预算
        history_budget = total_budget - sources_tokens

        if conversation_id:
            history = get_conversation_history(db, conversation_id, max_tokens=history_budget)
        else:
            conversation = Conversation(title=question[:50], user_id=user_id)
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
            conversation_id = conversation.id
            history = []

        user_msg = Message(
            conversation_id=conversation_id,
            role="user",
            content=question,
        )
        db.add(user_msg)
        db.commit()

        messages = build_messages(question, sources, history)
        model = get_chat_model()

        full_answer = ""
        async for chunk in model.astream(messages):
            content = chunk.content
            if content:
                full_answer += content
                yield f"event: token\ndata: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"

        if not full_answer:
            yield f"event: error\ndata: {json.dumps({'message': '模型未返回有效回答，请尝试重新提问'}, ensure_ascii=False)}\n\n"
            return

        sources_data = []
        for src in sources:
            meta = src["metadata"]
            sources_data.append({
                "file": meta.get("filename", "未知文件"),
                "page": meta.get("page"),
                "snippet": src["document"][:200],
                "doc_id": meta.get("doc_id"),
            })

        yield f"event: sources\ndata: {json.dumps({'sources': sources_data}, ensure_ascii=False)}\n\n"

        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=full_answer,
            sources=sources_data,
        )
        db.add(assistant_msg)
        db.commit()

        yield f"event: done\ndata: {json.dumps({'conversation_id': conversation_id})}\n\n"

    except Exception as e:
        logger.error(f"RAG 查询失败: {e}", exc_info=True)
        error_message = "抱歉，处理您的问题时出现错误"
        if "timeout" in str(e).lower() or "超时" in str(e):
            error_message = "LLM 服务响应超时，请稍后重试"
        elif "rate" in str(e).lower() or "limit" in str(e).lower():
            error_message = "LLM 服务请求过于频繁，请稍后重试"
        elif "auth" in str(e).lower() or "key" in str(e).lower():
            error_message = "LLM API Key 无效，请检查设置"
        yield f"event: error\ndata: {json.dumps({'message': error_message}, ensure_ascii=False)}\n\n"
