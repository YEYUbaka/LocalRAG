"""Query rewriting service: generates multiple search queries from a single user question."""

import logging
import re

from app.services.llm_service import get_chat_model
from app.core.prompts import build_rewrite_prompt
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


async def rewrite_query(question: str, num_queries: int = 3) -> list[str]:
    """Generate multiple search queries from a user question using LLM.

    Returns a list of queries including the original question.
    Falls back to just the original question on any error.
    """
    try:
        model = get_chat_model()
        prompt = build_rewrite_prompt(question)
        response = await model.ainvoke([HumanMessage(content=prompt)])

        # Parse response: split by newlines, filter empty
        lines = [line.strip() for line in response.content.strip().split("\n") if line.strip()]

        # Remove numbering if present (e.g., "1. xxx" -> "xxx")
        cleaned = []
        for line in lines:
            line = re.sub(r"^\d+[\.\)、]\s*", "", line)
            if line and line != question:
                cleaned.append(line)

        # Always include the original question
        queries = [question] + cleaned[:num_queries - 1]
        logger.info(f"Query rewrite: '%s' -> {queries}", question[:50])
        return queries

    except Exception as e:
        logger.warning(f"Query rewrite failed, using original: {e}")
        return [question]
