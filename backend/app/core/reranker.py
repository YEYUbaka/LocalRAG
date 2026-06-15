"""Reranker module using bge-reranker-v2-m3 for cross-encoder scoring."""

import logging
from pathlib import Path
from app.config import settings

logger = logging.getLogger(__name__)

_reranker = None


def get_reranker():
    """Lazy-load the reranker model singleton."""
    global _reranker
    if _reranker is None:
        model_path = settings.reranker_model_path
        logger.info(f"Loading reranker model from {model_path}...")
        try:
            from FlagEmbedding import FlagReranker
            _reranker = FlagReranker(model_path, use_fp16=True)
            logger.info("Reranker model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load reranker model: {e}")
            raise
    return _reranker


def rerank(query: str, documents: list[str]) -> list[float]:
    """Score query-document pairs using the reranker model.

    Returns a list of scores, one per document, in the same order.
    """
    if not documents:
        return []

    reranker = get_reranker()
    pairs = [[query, doc] for doc in documents]
    scores = reranker.compute_score(pairs)

    # compute_score returns a single float for 1 pair, or a list for multiple
    if isinstance(scores, (int, float)):
        return [float(scores)]
    return [float(s) for s in scores]
