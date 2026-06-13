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


class SettingsUpdate(BaseModel):
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model_name: str | None = None
    top_k: int | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    context_window: int | None = None
    similarity_threshold: float | None = None


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

    _save_overrides(settings)
    return _build_response()


@router.get("/health")
def health():
    return {"status": "ok"}
