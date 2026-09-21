import json
import logging
from collections.abc import AsyncGenerator

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from sqlalchemy.orm import Session

from app.core.vectorstore import hybrid_search, unified_search
from app.core.prompts import build_rag_prompt
from app.services.llm_service import get_chat_model, get_thinking_model
from app.services.web_search_service import web_search
from app.config import settings
from app.models import Conversation, Message
from app.domain.tenant import TenantScope

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


async def _try_web_search(question: str, sources: list[dict], kb_id: int | None) -> list[dict]:
    """当知识库无匹配结果时，尝试联网搜索。

    触发条件（满足任一）：
    1. sources 为空
    2. sources 中所有结果的 rerank 分数低于阈值（说明检索结果不相关）
    """
    if kb_id is None or not settings.web_search_enabled:
        return sources

    # 检查是否需要联网搜索：sources 为空，或所有结果 rerank 分数过低
    need_web = False
    if not sources:
        need_web = True
    elif settings.rerank_enabled and settings.rerank_threshold > 0:
        # 检查是否有高质量结果（rerank 分数 >= 阈值）
        # 注意：没有 rerank_score 的结果视为低质量（reranker 可能失败了）
        has_high_quality = any(
            src.get("rerank_score", -999.0) >= settings.rerank_threshold
            for src in sources
        )
        if not has_high_quality:
            need_web = True
            logger.info(
                f"All {len(sources)} sources below rerank threshold "
                f"({settings.rerank_threshold}), triggering web search"
            )

    if need_web:
        web_results = await web_search(question)
        if web_results:
            sources = [
                {
                    "id": f"web_{i}",
                    "document": f"{r['title']}\n{r['snippet']}",
                    "metadata": {"filename": r["title"], "page": None, "doc_id": None},
                    "type": "web",
                    "url": r["url"],
                }
                for i, r in enumerate(web_results)
            ]
            logger.info(f"Web search returned {len(sources)} results for: {question}")
    return sources


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


async def _retrieve_sources(
    question: str,
    scope: "TenantScope | None",
) -> list[dict]:
    """公共检索逻辑：查询改写 + 混合搜索 + 联网回退。"""
    if scope is None:
        return []
    if settings.unified_fusion_enabled:
        if settings.query_rewrite_enabled:
            from app.services.query_rewrite import rewrite_query

            queries = await rewrite_query(question)
        else:
            queries = [question]
        sources = unified_search(scope, question, queries)
    elif settings.query_rewrite_enabled:
        from app.services.query_rewrite import rewrite_query
        queries = await rewrite_query(question)

        all_sources = []
        seen_ids: set[str] = set()
        for q in queries:
            results = hybrid_search(scope, q)
            for r in results:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    all_sources.append(r)

        sources = all_sources[:settings.rerank_top_k]
    else:
        sources = hybrid_search(scope, question)

    sources = await _try_web_search(question, sources, scope.kb_id)
    return sources


async def rag_query(
    question: str,
    conversation_id: int | None,
    db: Session,
    scope: "TenantScope | None" = None,
    user_id: int | None = None,
) -> AsyncGenerator[str, None]:
    try:
        sources = await _retrieve_sources(question, scope)

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
            source_item = {
                "file": meta.get("filename", "未知文件"),
                "page": meta.get("page"),
                "snippet": src["document"][:200],
                "doc_id": meta.get("doc_id"),
                "type": src.get("type", "document"),
            }
            if src.get("url"):
                source_item["url"] = src["url"]
            sources_data.append(source_item)

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


async def rag_query_with_image(
    question: str,
    image_base64: str,
    conversation_id: int | None,
    db: Session,
    scope: "TenantScope | None" = None,
    user_id: int | None = None,
) -> AsyncGenerator[str, None]:
    """图片理解模式的 RAG 查询，使用视觉模型分析图片"""
    try:
        from app.services.llm_service import get_vision_model
        from langchain_core.messages import HumanMessage

        # 发送处理开始事件
        yield f"event: thinking\ndata: {json.dumps({'status': 'started', 'message': '正在分析图片...'}, ensure_ascii=False)}\n\n"

        # 构建包含图片的消息
        # LangChain 支持多模态消息格式
        content = [
            {"type": "text", "text": question},
            {
                "type": "image_url",
                "image_url": {
                    "url": image_base64,
                },
            },
        ]

        # 如果有知识库上下文，先检索相关内容
        sources = []
        if scope is not None:
            if settings.unified_fusion_enabled:
                sources = unified_search(scope, question, [question])
            else:
                sources = hybrid_search(scope, question)

        # 添加知识库上下文到问题中
        if sources:
            context = "\n\n".join([s["document"][:500] for s in sources[:3]])
            content[0]["text"] = f"基于以下知识库内容回答问题：\n\n{context}\n\n问题：{question}"

        # 处理会话历史
        if conversation_id:
            history = get_conversation_history(db, conversation_id)
        else:
            conversation = Conversation(title=f"[图片分析] {question[:50]}", user_id=user_id)
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
            conversation_id = conversation.id
            history = []

        # 保存用户消息
        user_msg = Message(
            conversation_id=conversation_id,
            role="user",
            content=f"[图片分析] {question}",
        )
        db.add(user_msg)
        db.commit()

        # 使用视觉模型
        model = get_vision_model()

        # 构建消息列表
        messages = []
        for msg in history:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))

        messages.append(HumanMessage(content=content))

        # 发送处理进度
        yield f"event: thinking\ndata: {json.dumps({'status': 'analyzing', 'message': '视觉模型正在分析图片...'}, ensure_ascii=False)}\n\n"

        full_answer = ""
        async for chunk in model.astream(messages):
            text = chunk.content
            if text:
                full_answer += text
                yield f"event: token\ndata: {json.dumps({'content': text}, ensure_ascii=False)}\n\n"

        if not full_answer:
            yield f"event: error\ndata: {json.dumps({'message': '模型未返回有效回答，请尝试重新提问'}, ensure_ascii=False)}\n\n"
            return

        # 发送来源信息
        sources_data = []
        for src in sources:
            meta = src["metadata"]
            sources_data.append({
                "file": meta.get("filename", "未知文件"),
                "page": meta.get("page"),
                "snippet": src["document"][:200],
                "doc_id": meta.get("doc_id"),
            })

        if sources_data:
            yield f"event: sources\ndata: {json.dumps({'sources': sources_data}, ensure_ascii=False)}\n\n"

        # 保存助手消息
        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=full_answer,
            sources=sources_data if sources_data else None,
        )
        db.add(assistant_msg)
        db.commit()

        yield f"event: done\ndata: {json.dumps({'conversation_id': conversation_id})}\n\n"

    except Exception as e:
        logger.error(f"图片理解查询失败: {e}", exc_info=True)
        error_message = "抱歉，图片分析时出现错误"
        if "timeout" in str(e).lower() or "超时" in str(e):
            error_message = "图片分析超时，请稍后重试"
        elif "rate" in str(e).lower() or "limit" in str(e).lower():
            error_message = "LLM 服务请求过于频繁，请稍后重试"
        elif "auth" in str(e).lower() or "key" in str(e).lower():
            error_message = "LLM API Key 无效，请检查设置"
        yield f"event: error\ndata: {json.dumps({'message': error_message}, ensure_ascii=False)}\n\n"


async def rag_query_with_thinking(
    question: str,
    conversation_id: int | None,
    db: Session,
    scope: "TenantScope | None" = None,
    user_id: int | None = None,
) -> AsyncGenerator[str, None]:
    """深度思考模式的 RAG 查询，使用更强大的模型和更长的推理时间"""
    try:
        # 发送思考开始事件
        yield f"event: thinking\ndata: {json.dumps({'status': 'started', 'message': '正在深度思考中...'}, ensure_ascii=False)}\n\n"

        sources = await _retrieve_sources(question, scope)

        # 计算 token 预算
        context_window = getattr(settings, 'context_window', DEFAULT_CONTEXT_WINDOW)
        total_budget = int(context_window * TOKEN_BUDGET_RATIO)

        sources_text = " ".join(s["document"] for s in sources)
        sources_tokens = estimate_tokens(sources_text)
        history_budget = total_budget - sources_tokens

        if conversation_id:
            history = get_conversation_history(db, conversation_id, max_tokens=history_budget)
        else:
            conversation = Conversation(title=f"[深度思考] {question[:50]}", user_id=user_id)
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
            conversation_id = conversation.id
            history = []

        user_msg = Message(
            conversation_id=conversation_id,
            role="user",
            content=f"[深度思考模式] {question}",
        )
        db.add(user_msg)
        db.commit()

        messages = build_messages(question, sources, history)

        # 使用深度思考模型
        model = get_thinking_model()

        # 发送思考进度
        yield f"event: thinking\ndata: {json.dumps({'status': 'reasoning', 'message': '正在深度推理中，请耐心等待...'}, ensure_ascii=False)}\n\n"

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
            source_item = {
                "file": meta.get("filename", "未知文件"),
                "page": meta.get("page"),
                "snippet": src["document"][:200],
                "doc_id": meta.get("doc_id"),
                "type": src.get("type", "document"),
            }
            if src.get("url"):
                source_item["url"] = src["url"]
            sources_data.append(source_item)

        yield f"event: sources\ndata: {json.dumps({'sources': sources_data}, ensure_ascii=False)}\n\n"

        # 发送思考完成
        yield f"event: thinking\ndata: {json.dumps({'status': 'completed', 'message': '深度思考完成'}, ensure_ascii=False)}\n\n"

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
        logger.error(f"深度思考查询失败: {e}", exc_info=True)
        error_message = "抱歉，深度思考处理时出现错误"
        if "timeout" in str(e).lower() or "超时" in str(e):
            error_message = "深度思考超时，请稍后重试（复杂问题可能需要更长时间）"
        elif "rate" in str(e).lower() or "limit" in str(e).lower():
            error_message = "LLM 服务请求过于频繁，请稍后重试"
        elif "auth" in str(e).lower() or "key" in str(e).lower():
            error_message = "LLM API Key 无效，请检查设置"
        yield f"event: error\ndata: {json.dumps({'message': error_message}, ensure_ascii=False)}\n\n"
