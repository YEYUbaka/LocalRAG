import json
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


PERSISTED_FIELDS = {
    "llm_base_url", "llm_model_name",
    "top_k", "temperature", "max_tokens", "context_window",
    "similarity_threshold", "max_upload_size",
    "hybrid_search", "bm25_weight", "retrieval_top_k", "rerank_top_k",
    "rerank_enabled", "rerank_threshold", "query_rewrite_enabled",
    "web_search_enabled",
}


class Settings(BaseSettings):
    # LLM (OpenAI 兼容格式，支持 Qwen/DeepSeek/Moonshot/Ollama 等)
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str = ""
    llm_model_name: str = "qwen-max"

    # Embedding
    embedding_model_name: str = "bge-small-zh-v1.5"
    embedding_model_path: str = str(Path(__file__).parent.parent.parent / "data" / "models" / "AI-ModelScope" / "bge-small-zh-v1___5")

    # RAG
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 5
    temperature: float = 0.7
    max_tokens: int = 2048
    context_window: int = 8192
    similarity_threshold: float = 0.7

    # Upload
    max_upload_size: int = 50 * 1024 * 1024  # 50MB

    # Hybrid Search
    hybrid_search: bool = True
    bm25_weight: float = 0.5
    retrieval_top_k: int = 20
    rerank_top_k: int = 5

    # Feature-flagged multi-query retrieval experiments. These are intentionally
    # not persisted through the user settings API while the baseline is frozen.
    unified_fusion_enabled: bool = False
    post_fusion_similarity_filter_enabled: bool = False

    # Reranker
    rerank_enabled: bool = True
    rerank_threshold: float = 1.0

    # Query Rewrite
    query_rewrite_enabled: bool = True

    # Web Search
    web_search_enabled: bool = False
    reranker_model_path: str = str(Path(__file__).parent.parent.parent / "data" / "models" / "BAAI" / "bge-reranker-v2-m3")

    # Data
    data_dir: str = "./data"

    # MySQL
    database_url: str = "mysql+pymysql://root:password@localhost:3306/localrag"

    @property
    def uploads_dir(self) -> Path:
        return Path(self.data_dir) / "uploads"

    @property
    def chromadb_dir(self) -> Path:
        return Path(self.data_dir) / "chromadb"

    @property
    def settings_file(self) -> Path:
        return Path(self.data_dir) / "settings.json"

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
    )


def _load_overrides(s: Settings) -> None:
    """Load persisted settings from JSON file, overriding defaults."""
    path = s.settings_file
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Never load persisted secret material back into settings
        data.pop("llm_api_key", None)
        for key, value in data.items():
            if key in PERSISTED_FIELDS and hasattr(s, key):
                setattr(s, key, value)
    except (json.JSONDecodeError, OSError):
        pass  # Ignore corrupted settings file


def _save_overrides(s: Settings) -> None:
    """Save persisted settings to JSON file."""
    data = {key: getattr(s, key) for key in PERSISTED_FIELDS if hasattr(s, key)}
    path = s.settings_file
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


settings = Settings()
_load_overrides(settings)
