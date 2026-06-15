from datetime import datetime

RAG_SYSTEM_PROMPT = """你是一个知识库问答助手。请根据下方提供的知识库内容回答用户的问题。

规则：
1. 仔细阅读知识库内容，从中提取与问题相关的信息来回答
2. 只有当知识库内容确实与问题完全无关时，才可以回答"知识库中未包含相关内容"
3. 回答时请引用来源，格式为 [来源N]，N 为片段编号
4. 回答要简洁、准确、有条理
5. 如果问题涉及多个方面，请分点回答

以下是检索到的相关知识库内容：

{context}
"""


def _get_general_prompt() -> str:
    now = datetime.now()
    return f"""你是一个智能助手。请直接回答用户的问题，就像普通 AI 对话一样。
不要提及"知识库"，不要说"未找到相关信息"。
正常聊天、回答问题、提供帮助。

当前时间：{now.strftime('%Y年%m月%d日 %H:%M')}"""


def format_context(sources: list[dict]) -> str:
    parts = []
    for i, src in enumerate(sources, 1):
        meta = src["metadata"]
        filename = meta.get("filename", "未知文件")
        page = meta.get("page", "")
        page_info = f"，第{page}页" if page else ""
        parts.append(f"[来源{i}] 来自《{filename}》{page_info}：\n{src['document']}")
    return "\n\n".join(parts)


QUERY_REWRITE_PROMPT = """你是一个查询改写助手。用户的问题可能模糊或口语化。
请将以下问题改写为 2-3 个不同角度的搜索查询，每行一个。
要求：
- 保持原始意图
- 使用不同的表述方式
- 包含同义词或相关术语
- 不要添加编号或前缀

原始问题：{question}

改写后的查询（每行一个）："""


def build_rewrite_prompt(question: str) -> str:
    return QUERY_REWRITE_PROMPT.format(question=question)


def build_rag_prompt(question: str, sources: list[dict]) -> str:
    if not sources:
        return _get_general_prompt()
    context = format_context(sources)
    return RAG_SYSTEM_PROMPT.format(context=context)
