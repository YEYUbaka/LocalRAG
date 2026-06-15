from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings, _save_overrides

router = APIRouter(prefix="/api", tags=["settings"])


class SettingsResponse(BaseModel):
    llm_base_url: str
    llm_model_name: str
    embedding_model_name: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    temperature: float
    max_tokens: int
    context_window: int
    similarity_threshold: float
    hybrid_search: bool
    bm25_weight: float
    retrieval_top_k: int
    rerank_top_k: int
    rerank_enabled: bool
    query_rewrite_enabled: bool


class SettingsUpdate(BaseModel):
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model_name: str | None = None
    top_k: int | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    context_window: int | None = None
    similarity_threshold: float | None = None
    hybrid_search: bool | None = None
    bm25_weight: float | None = None
    retrieval_top_k: int | None = None
    rerank_top_k: int | None = None
    rerank_enabled: bool | None = None
    query_rewrite_enabled: bool | None = None


def _build_response() -> SettingsResponse:
    return SettingsResponse(
        llm_base_url=settings.llm_base_url,
        llm_model_name=settings.llm_model_name,
        embedding_model_name=settings.embedding_model_name,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        top_k=settings.top_k,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        context_window=settings.context_window,
        similarity_threshold=settings.similarity_threshold,
        hybrid_search=settings.hybrid_search,
        bm25_weight=settings.bm25_weight,
        retrieval_top_k=settings.retrieval_top_k,
        rerank_top_k=settings.rerank_top_k,
        rerank_enabled=settings.rerank_enabled,
        query_rewrite_enabled=settings.query_rewrite_enabled,
    )


@router.get("/settings", response_model=SettingsResponse)
def get_settings():
    return _build_response()


@router.put("/settings", response_model=SettingsResponse)
def update_settings(update: SettingsUpdate):
    if update.llm_base_url is not None:
        settings.llm_base_url = update.llm_base_url
    if update.llm_api_key is not None:
        settings.llm_api_key = update.llm_api_key
    if update.llm_model_name is not None:
        settings.llm_model_name = update.llm_model_name
    if update.top_k is not None:
        settings.top_k = update.top_k
    if update.temperature is not None:
        settings.temperature = update.temperature
    if update.max_tokens is not None:
        settings.max_tokens = update.max_tokens
    if update.context_window is not None:
        settings.context_window = update.context_window
    if update.similarity_threshold is not None:
        settings.similarity_threshold = update.similarity_threshold
    if update.hybrid_search is not None:
        settings.hybrid_search = update.hybrid_search
    if update.bm25_weight is not None:
        settings.bm25_weight = update.bm25_weight
    if update.retrieval_top_k is not None:
        settings.retrieval_top_k = update.retrieval_top_k
    if update.rerank_top_k is not None:
        settings.rerank_top_k = update.rerank_top_k
    if update.rerank_enabled is not None:
        settings.rerank_enabled = update.rerank_enabled
    if update.query_rewrite_enabled is not None:
        settings.query_rewrite_enabled = update.query_rewrite_enabled

    _save_overrides(settings)
    return _build_response()


@router.get("/health")
def health():
    return {"status": "ok"}
