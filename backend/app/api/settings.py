import os
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.auth import require_owner
from app.config import settings, _save_overrides, PERSISTED_FIELDS

router = APIRouter(prefix="/api", tags=["settings"])


def _llm_api_key_configured() -> bool:
    value = os.environ.get("LLM_API_KEY", "")
    return bool(value)


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
    rerank_threshold: float
    query_rewrite_enabled: bool
    web_search_enabled: bool
    llm_api_key_configured: bool


class SettingsUpdate(BaseModel):
    llm_base_url: str | None = None
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
    rerank_threshold: float | None = None
    query_rewrite_enabled: bool | None = None
    web_search_enabled: bool | None = None

    @field_validator("llm_base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parsed = urlparse(value)
        if parsed.scheme != "https":
            raise ValueError("LLM Base URL 必须是 HTTPS 地址")
        if parsed.username or parsed.password:
            raise ValueError("LLM Base URL 不能包含用户信息")
        if parsed.fragment:
            raise ValueError("LLM Base URL 不能包含片段")
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("LLM Base URL 缺少主机名")
        allowed = os.environ.get("LLM_ALLOWED_HOSTS", "dashscope.aliyuncs.com,api.deepseek.com,api.moonshot.cn,ark.cn-beijing.volces.com,api.openai.com,localhost")
        if hostname not in {h.strip() for h in allowed.split(",")}:
            raise ValueError("LLM Base URL 主机不在允许列表内")
        port = parsed.port
        if port is not None and port != 443:
            raise ValueError("LLM Base URL 端口必须为 443")
        return value


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
        rerank_threshold=settings.rerank_threshold,
        query_rewrite_enabled=settings.query_rewrite_enabled,
        web_search_enabled=settings.web_search_enabled,
        llm_api_key_configured=_llm_api_key_configured(),
    )


@router.get("/settings", response_model=SettingsResponse, dependencies=[Depends(require_owner)])
def get_settings():
    return _build_response()


@router.put("/settings", response_model=SettingsResponse, dependencies=[Depends(require_owner)])
def update_settings(update: SettingsUpdate):
    if update.llm_base_url is not None:
        settings.llm_base_url = update.llm_base_url
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
    if update.rerank_threshold is not None:
        settings.rerank_threshold = update.rerank_threshold
    if update.query_rewrite_enabled is not None:
        settings.query_rewrite_enabled = update.query_rewrite_enabled
    if update.web_search_enabled is not None:
        settings.web_search_enabled = update.web_search_enabled

    _save_overrides(settings)
    return _build_response()


@router.get("/health")
def health():
    return {"status": "ok"}
