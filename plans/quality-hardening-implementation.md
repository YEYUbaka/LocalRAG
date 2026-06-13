# Quality Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement settings persistence, file upload security, and hybrid BM25+vector search for LocalRAG.

**Architecture:** Three independent features executed sequentially. Settings persistence uses JSON file storage. File upload security adds validation at the API layer. Hybrid search adds BM25 index with RRF fusion alongside existing ChromaDB vector search.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, ChromaDB, rank_bm25, jieba, React, Ant Design

**Spec:** `docs/superpowers/specs/2026-06-13-quality-hardening-design.md`

---

## File Map

| File | Action | Feature |
|------|--------|---------|
| `backend/app/config.py` | Modify | All three |
| `backend/app/api/settings.py` | Modify | Settings persistence + Hybrid search |
| `backend/app/api/documents.py` | Modify | File upload security |
| `backend/app/core/vectorstore.py` | Modify | Hybrid search |
| `backend/app/core/bm25_search.py` | Create | Hybrid search |
| `backend/app/services/rag_service.py` | Modify | Hybrid search |
| `backend/app/services/document_service.py` | Modify | Hybrid search |
| `backend/requirements.txt` | Modify | Hybrid search |
| `frontend/src/types/index.ts` | Modify | All three |
| `frontend/src/components/SettingsPanel.tsx` | Modify | All three |

---

## Feature 1: Settings Persistence

### Task 1.1: Add `similarity_threshold` and `_load_overrides` to Settings

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add new fields and override logic to config.py**

Replace the entire `config.py` with:

```python
import json
from pydantic_settings import BaseSettings
from pathlib import Path


PERSISTED_FIELDS = {
    "llm_base_url", "llm_api_key", "llm_model_name",
    "top_k", "temperature", "max_tokens", "context_window",
    "similarity_threshold",
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

    class Config:
        env_file = str(Path(__file__).parent.parent.parent / ".env")
        env_file_encoding = "utf-8"


def _load_overrides(s: Settings) -> None:
    """Load persisted settings from JSON file, overriding defaults."""
    path = s.settings_file
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
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
```

- [ ] **Step 2: Verify the server starts cleanly**

Run: `cd e:/AI_projects/LocalRAG/backend && python -c "from app.config import settings; print(settings.similarity_threshold, settings.settings_file)"`
Expected: `0.7 e:\AI_projects\LocalRAG\data\settings.json`

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: add settings persistence with JSON file storage"
```

---

### Task 1.2: Update settings API to persist changes

**Files:**
- Modify: `backend/app/api/settings.py`

- [ ] **Step 1: Update settings.py with new fields and persistence**

Replace the entire `settings.py` with:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/settings.py
git commit -m "feat: persist settings to JSON on PUT and add similarity_threshold"
```

---

### Task 1.3: Update frontend types and SettingsPanel

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/SettingsPanel.tsx`

- [ ] **Step 1: Add similarity_threshold to Settings interface**

In `frontend/src/types/index.ts`, add `similarity_threshold` to the `Settings` interface:

```typescript
export interface Settings {
  llm_base_url: string;
  llm_model_name: string;
  embedding_model_name: string;
  chunk_size: number;
  chunk_overlap: number;
  top_k: number;
  temperature: number;
  max_tokens: number;
  context_window: number;
  similarity_threshold: number;
}
```

- [ ] **Step 2: Add similarity_threshold slider to SettingsPanel**

In `frontend/src/components/SettingsPanel.tsx`, add the slider after the "上下文窗口大小" `Form.Item` (before the save button `Form.Item`):

```tsx
<Form.Item label="相似度阈值" tooltip="检索结果的最低相似度，越高越严格">
  <Slider
    min={0}
    max={1}
    step={0.05}
    value={settings.similarity_threshold}
    onChange={(v) => setSettings({ ...settings, similarity_threshold: v })}
    marks={{ 0: '0', 0.5: '0.5', 0.7: '0.7', 1: '1' }}
  />
</Form.Item>
```

Also add `similarity_threshold` to the `handleSave` payload:

```typescript
const payload: any = {
  llm_base_url: settings.llm_base_url,
  llm_model_name: settings.llm_model_name,
  top_k: settings.top_k,
  temperature: settings.temperature,
  max_tokens: settings.max_tokens,
  context_window: settings.context_window,
  similarity_threshold: settings.similarity_threshold,
};
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/components/SettingsPanel.tsx
git commit -m "feat: add similarity_threshold slider to settings panel"
```

---

### Task 1.4: Use `similarity_threshold` from settings in vectorstore

**Files:**
- Modify: `backend/app/core/vectorstore.py`

- [ ] **Step 1: Replace hardcoded threshold**

In `backend/app/core/vectorstore.py`, remove the hardcoded `SIMILARITY_THRESHOLD = 1.0` and use `settings.similarity_threshold` in the `search` function:

```python
# Remove this line:
# SIMILARITY_THRESHOLD = 1.0

# In search(), change:
#     if dist > SIMILARITY_THRESHOLD:
# to:
#     if dist > settings.similarity_threshold:
```

The updated `search` function:

```python
def search(query: str, top_k: int | None = None) -> list[dict]:
    collection = get_collection()
    if collection.count() == 0:
        return []

    k = top_k or settings.top_k
    query_embedding = embed_texts([query])
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    if not results["ids"][0]:
        return []

    items = []
    for i in range(len(results["ids"][0])):
        dist = results["distances"][0][i]
        if dist > settings.similarity_threshold:
            continue
        items.append({
            "id": results["ids"][0][i],
            "document": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": dist,
        })
    return items
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/vectorstore.py
git commit -m "feat: use configurable similarity_threshold instead of hardcoded 1.0"
```

---

## Feature 2: File Upload Security

### Task 2.1: Add `max_upload_size` to config

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add max_upload_size field**

In `backend/app/config.py`, add to the `Settings` class after `similarity_threshold`:

```python
    # Upload
    max_upload_size: int = 50 * 1024 * 1024  # 50MB
```

Also add `"max_upload_size"` to the `PERSISTED_FIELDS` set.

- [ ] **Step 2: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: add max_upload_size config (50MB default)"
```

---

### Task 2.2: Secure the upload endpoint

**Files:**
- Modify: `backend/app/api/documents.py`

- [ ] **Step 1: Rewrite upload endpoint with security checks**

Replace the `upload_document` function in `backend/app/api/documents.py`:

```python
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Document
from app.services.document_service import compute_md5, process_document, delete_document, LOADER_MAP

router = APIRouter(prefix="/api/documents", tags=["documents"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sanitize_filename(filename: str) -> str:
    """Remove unsafe characters from filename, keeping Chinese, letters, digits, dots, underscores, hyphens."""
    name = re.sub(r'[^\w一-鿿._-]', '', filename)
    return name or "unnamed"


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # 1. Check file size
    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过限制（最大 {settings.max_upload_size // 1024 // 1024}MB）",
        )

    # 2. Check extension
    original_filename = file.filename or "unnamed"
    suffix = Path(original_filename).suffix.lower()
    if suffix not in LOADER_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {suffix}",
        )

    # 3. Generate safe filename with UUID
    safe_name = _sanitize_filename(Path(original_filename).stem)
    stored_filename = f"{uuid.uuid4().hex}_{safe_name}{suffix}"

    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = settings.uploads_dir / stored_filename

    with open(file_path, "wb") as f:
        f.write(content)

    # 4. Check for duplicates
    md5 = compute_md5(file_path)
    existing = db.query(Document).filter(Document.md5_hash == md5).first()
    if existing:
        file_path.unlink()
        raise HTTPException(status_code=409, detail=f"文档已存在: {existing.filename}")

    # 5. Create record (store original filename for display, safe path for storage)
    doc = Document(
        filename=original_filename,
        file_path=str(file_path),
        file_size=len(content),
        md5_hash=md5,
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    from app.main import SessionLocal as Factory
    background_tasks.add_task(process_document, doc.id, Factory)

    return {"id": doc.id, "filename": doc.filename, "status": doc.status}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/documents.py
git commit -m "feat: secure file upload with size limit, UUID rename, and extension check"
```

---

## Feature 3: Hybrid Search (BM25 + Vector)

### Task 3.1: Add `rank_bm25` dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add rank_bm25 to requirements.txt**

Append to `backend/requirements.txt`:

```
rank_bm25==0.2.2
```

- [ ] **Step 2: Install the dependency**

Run: `cd e:/AI_projects/LocalRAG/backend && pip install rank_bm25==0.2.2`

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "feat: add rank_bm25 dependency for hybrid search"
```

---

### Task 3.2: Add hybrid search config fields

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add hybrid search fields to Settings**

In `backend/app/config.py`, add to the `Settings` class after `similarity_threshold`:

```python
    # Hybrid Search
    hybrid_search: bool = True
    bm25_weight: float = 0.5
    retrieval_top_k: int = 20
    rerank_top_k: int = 5
```

Add these fields to `PERSISTED_FIELDS`:

```python
PERSISTED_FIELDS = {
    "llm_base_url", "llm_api_key", "llm_model_name",
    "top_k", "temperature", "max_tokens", "context_window",
    "similarity_threshold", "max_upload_size",
    "hybrid_search", "bm25_weight", "retrieval_top_k", "rerank_top_k",
}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: add hybrid search config fields"
```

---

### Task 3.3: Create BM25 search module

**Files:**
- Create: `backend/app/core/bm25_search.py`

- [ ] **Step 1: Create bm25_search.py**

```python
"""BM25 keyword search index for hybrid retrieval."""

import logging
from rank_bm25 import BM25Okapi
import jieba

logger = logging.getLogger(__name__)

# doc_id -> list of chunk texts
_chunk_store: dict[int, list[str]] = {}
# doc_id -> BM25Okapi instance (built lazily)
_bm25_index: BM25Okapi | None = None
_corpus: list[tuple[int, str]] = []  # [(doc_id, chunk_text), ...]
_dirty = True


def _tokenize(text: str) -> list[str]:
    """Tokenize Chinese text using jieba."""
    return list(jieba.cut(text))


def _rebuild_index() -> None:
    """Rebuild the BM25 index from all stored chunks."""
    global _bm25_index, _corpus, _dirty
    _corpus = []
    for doc_id, chunks in _chunk_store.items():
        for chunk in chunks:
            _corpus.append((doc_id, chunk))

    if not _corpus:
        _bm25_index = None
        _dirty = False
        return

    tokenized = [_tokenize(text) for _, text in _corpus]
    _bm25_index = BM25Okapi(tokenized)
    _dirty = False
    logger.info(f"BM25 index rebuilt: {len(_corpus)} chunks from {len(_chunk_store)} documents")


def add_document_chunks(doc_id: int, chunks: list[str]) -> None:
    """Add chunks for a document to the BM25 index."""
    global _dirty
    try:
        _chunk_store[doc_id] = chunks
        _dirty = True
    except Exception as e:
        logger.warning(f"BM25: failed to add chunks for doc {doc_id}: {e}")


def remove_document(doc_id: int) -> None:
    """Remove a document's chunks from the BM25 index."""
    global _dirty
    try:
        if doc_id in _chunk_store:
            del _chunk_store[doc_id]
            _dirty = True
    except Exception as e:
        logger.warning(f"BM25: failed to remove doc {doc_id}: {e}")


def bm25_search(query: str, top_k: int = 20) -> list[dict]:
    """Search using BM25 keyword matching. Returns list of {id, document, metadata}."""
    global _dirty
    if _dirty:
        _rebuild_index()

    if _bm25_index is None or not _corpus:
        return []

    tokenized_query = _tokenize(query)
    scores = _bm25_index.get_scores(tokenized_query)

    # Get top-k indices by score
    ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

    results = []
    for idx in ranked_indices:
        if scores[idx] <= 0:
            continue
        doc_id, text = _corpus[idx]
        results.append({
            "id": f"doc_{doc_id}_chunk_{idx}",
            "document": text,
            "doc_id": doc_id,
            "bm25_score": float(scores[idx]),
        })

    return results


def rebuild_from_db(db_session_factory) -> None:
    """Rebuild BM25 index from all completed documents in the database."""
    from app.models import Document
    db = db_session_factory()
    try:
        docs = db.query(Document).filter(Document.status == "completed").all()
        for doc in docs:
            if doc.parsed_content:
                # Split parsed_content back into chunks for BM25
                # We use a simple split since the exact chunk boundaries aren't stored separately
                from app.services.document_service import split_documents, parse_document
                from pathlib import Path
                try:
                    file_path = Path(doc.file_path)
                    if file_path.exists():
                        raw_docs = parse_document(file_path)
                        texts, _ = split_documents(raw_docs, doc.filename)
                        add_document_chunks(doc.id, texts)
                except Exception as e:
                    logger.warning(f"BM25: failed to rebuild for doc {doc.id}: {e}")
        _rebuild_index()
        logger.info(f"BM25 index rebuilt from DB: {len(_chunk_store)} documents")
    finally:
        db.close()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/bm25_search.py
git commit -m "feat: add BM25 search module with jieba tokenization"
```

---

### Task 3.4: Update vectorstore with hybrid search

**Files:**
- Modify: `backend/app/core/vectorstore.py`

- [ ] **Step 1: Add hybrid_search function to vectorstore.py**

Replace the entire `vectorstore.py`:

```python
import chromadb
from app.config import settings
from app.core.embedding import embed_texts

_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None

COLLECTION_NAME = "localrag"


def get_chroma_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        settings.chromadb_dir.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(settings.chromadb_dir))
    return _client


def get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def add_documents(doc_id: int, texts: list[str], metadatas: list[dict]) -> None:
    collection = get_collection()
    embeddings = embed_texts(texts)
    ids = [f"doc_{doc_id}_chunk_{i}" for i in range(len(texts))]
    metadata_with_doc = [{**m, "doc_id": doc_id} for m in metadatas]
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadata_with_doc,
    )


def vector_search(query: str, top_k: int | None = None) -> list[dict]:
    """Pure vector search using ChromaDB."""
    collection = get_collection()
    if collection.count() == 0:
        return []

    k = top_k or settings.retrieval_top_k
    query_embedding = embed_texts([query])
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    if not results["ids"][0]:
        return []

    items = []
    for i in range(len(results["ids"][0])):
        dist = results["distances"][0][i]
        if dist > settings.similarity_threshold:
            continue
        items.append({
            "id": results["ids"][0][i],
            "document": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": dist,
        })
    return items


def rrf_fusion(
    vector_results: list[dict],
    bm25_results: list[dict],
    vector_weight: float = 0.5,
    bm25_weight: float = 0.5,
    k: int = 60,
    top_n: int = 5,
) -> list[dict]:
    """Reciprocal Rank Fusion of vector and BM25 results."""
    # Build a lookup for metadata from vector results
    doc_lookup: dict[str, dict] = {}
    for item in vector_results:
        doc_lookup[item["id"]] = item

    scores: dict[str, float] = {}
    for rank, item in enumerate(vector_results):
        doc_id = item["id"]
        scores[doc_id] = scores.get(doc_id, 0) + vector_weight / (k + rank)

    for rank, item in enumerate(bm25_results):
        doc_id = item["id"]
        if doc_id not in doc_lookup:
            # For BM25-only results, we need to fetch metadata from ChromaDB
            doc_lookup[doc_id] = {
                "id": doc_id,
                "document": item["document"],
                "metadata": {"doc_id": item.get("doc_id")},
            }
        scores[doc_id] = scores.get(doc_id, 0) + bm25_weight / (k + rank)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [doc_lookup[doc_id] for doc_id, _ in ranked if doc_id in doc_lookup]


def hybrid_search(query: str) -> list[dict]:
    """Hybrid search: vector + BM25 with RRF fusion, or pure vector if hybrid is disabled."""
    if not settings.hybrid_search:
        return vector_search(query, top_k=settings.rerank_top_k)

    from app.core.bm25_search import bm25_search

    retrieval_k = settings.retrieval_top_k
    vector_results = vector_search(query, top_k=retrieval_k)
    bm25_results = bm25_search(query, top_k=retrieval_k)

    if not bm25_results:
        return vector_results[:settings.rerank_top_k]
    if not vector_results:
        return []

    vector_weight = 1 - settings.bm25_weight
    return rrf_fusion(
        vector_results,
        bm25_results,
        vector_weight=vector_weight,
        bm25_weight=settings.bm25_weight,
        top_n=settings.rerank_top_k,
    )


# Keep backward-compatible search function
def search(query: str, top_k: int | None = None) -> list[dict]:
    """Main search entry point. Uses hybrid_search when enabled."""
    if top_k is not None:
        # Direct call with specific top_k (e.g., from tests) - use vector only
        return vector_search(query, top_k=top_k)
    return hybrid_search(query)


def delete_by_doc_id(doc_id: int) -> None:
    collection = get_collection()
    collection.delete(where={"doc_id": doc_id})
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/vectorstore.py
git commit -m "feat: implement hybrid search with RRF fusion"
```

---

### Task 3.5: Update document service to sync BM25 index

**Files:**
- Modify: `backend/app/services/document_service.py`

- [ ] **Step 1: Add BM25 sync to process_document and delete_document**

In `backend/app/services/document_service.py`, update `process_document` to sync BM25 after successful processing:

```python
def process_document(doc_id: int, db_session_factory) -> None:
    """BackgroundTasks 回调：解析文档并入库"""
    db: Session = db_session_factory()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return

        doc.status = "processing"
        db.commit()

        file_path = Path(doc.file_path)
        raw_docs = parse_document(file_path)

        # Save parsed content and page breaks
        doc.parsed_content = "\n\n".join(d.page_content for d in raw_docs)
        doc.page_breaks = compute_page_breaks(raw_docs)

        texts, metadatas = split_documents(raw_docs, doc.filename)
        doc.chunk_count = len(texts)

        add_documents(doc_id, texts, metadatas)

        # Sync BM25 index
        try:
            from app.core.bm25_search import add_document_chunks
            add_document_chunks(doc_id, texts)
        except Exception as e:
            logger.warning(f"BM25 sync failed for doc {doc_id}: {e}")

        doc.status = "completed"
        db.commit()
    except Exception as e:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.status = "failed"
            doc.error_message = str(e)
            db.commit()
    finally:
        db.close()
```

Update `delete_document` to remove from BM25:

```python
def delete_document(doc_id: int, db: Session) -> None:
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise ValueError(f"文档 {doc_id} 不存在")

    delete_by_doc_id(doc_id)

    # Remove from BM25 index
    try:
        from app.core.bm25_search import remove_document
        remove_document(doc_id)
    except Exception:
        pass

    file_path = Path(doc.file_path)
    if file_path.exists():
        file_path.unlink()

    db.delete(doc)
    db.commit()
```

Also add `import logging` and `logger = logging.getLogger(__name__)` at the top of the file.

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/document_service.py
git commit -m "feat: sync BM25 index on document add/delete"
```

---

### Task 3.6: Update rag_service to use hybrid_search

**Files:**
- Modify: `backend/app/services/rag_service.py`

- [ ] **Step 1: Update rag_service imports and search call**

In `backend/app/services/rag_service.py`, change the import and search call:

Change:
```python
from app.core.vectorstore import search
```
To:
```python
from app.core.vectorstore import hybrid_search
```

Change in `rag_query`:
```python
        sources = search(question)
```
To:
```python
        sources = hybrid_search(question)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/rag_service.py
git commit -m "feat: use hybrid_search in rag_service"
```

---

### Task 3.7: Add BM25 index rebuild on startup

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add startup event to rebuild BM25 index**

Read `backend/app/main.py` first, then add a startup event. Find where the FastAPI app is created and add:

```python
@app.on_event("startup")
async def rebuild_bm25_index():
    """Rebuild BM25 index from database on startup."""
    try:
        from app.core.bm25_search import rebuild_from_db
        rebuild_from_db(SessionLocal)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"BM25 index rebuild failed: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: rebuild BM25 index on server startup"
```

---

### Task 3.8: Update frontend for hybrid search settings

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/SettingsPanel.tsx`

- [ ] **Step 1: Add hybrid search fields to Settings interface**

In `frontend/src/types/index.ts`, update the `Settings` interface:

```typescript
export interface Settings {
  llm_base_url: string;
  llm_model_name: string;
  embedding_model_name: string;
  chunk_size: number;
  chunk_overlap: number;
  top_k: number;
  temperature: number;
  max_tokens: number;
  context_window: number;
  similarity_threshold: number;
  hybrid_search: boolean;
  bm25_weight: number;
  retrieval_top_k: number;
  rerank_top_k: number;
}
```

- [ ] **Step 2: Add hybrid search controls to SettingsPanel**

In `frontend/src/components/SettingsPanel.tsx`, add `Switch` to the imports:

```typescript
import { Form, Input, Slider, InputNumber, Button, message, Space, Typography, Switch } from 'antd';
```

Replace the "检索数量 (Top-K)" Form.Item with the new hybrid search controls. Add after the "模型名称" Form.Item:

```tsx
<Form.Item label="启用混合检索" tooltip="BM25 关键词检索 + 向量语义检索，提升召回质量">
  <Switch
    checked={settings.hybrid_search}
    onChange={(v) => setSettings({ ...settings, hybrid_search: v })}
  />
</Form.Item>

{settings.hybrid_search && (
  <>
    <Form.Item label="BM25 权重" tooltip="BM25 关键词检索的权重，向量权重 = 1 - BM25 权重">
      <Slider
        min={0}
        max={1}
        step={0.1}
        value={settings.bm25_weight}
        onChange={(v) => setSettings({ ...settings, bm25_weight: v })}
        marks={{ 0: '0', 0.5: '0.5', 1: '1' }}
      />
    </Form.Item>

    <Form.Item label="粗检索数量" tooltip="每路检索返回的候选数量">
      <InputNumber
        min={5}
        max={50}
        value={settings.retrieval_top_k}
        onChange={(v) => setSettings({ ...settings, retrieval_top_k: v || 20 })}
        style={{ width: '100%' }}
      />
    </Form.Item>
  </>
)}

<Form.Item label="最终返回数量" tooltip="返回给用户的检索结果数量">
  <Slider
    min={1}
    max={10}
    value={settings.rerank_top_k}
    onChange={(v) => setSettings({ ...settings, rerank_top_k: v })}
    marks={{ 1: '1', 5: '5', 10: '10' }}
  />
</Form.Item>
```

- [ ] **Step 3: Update handleSave payload**

Update the `handleSave` payload in `SettingsPanel.tsx`:

```typescript
const payload: any = {
  llm_base_url: settings.llm_base_url,
  llm_model_name: settings.llm_model_name,
  temperature: settings.temperature,
  max_tokens: settings.max_tokens,
  context_window: settings.context_window,
  similarity_threshold: settings.similarity_threshold,
  hybrid_search: settings.hybrid_search,
  bm25_weight: settings.bm25_weight,
  retrieval_top_k: settings.retrieval_top_k,
  rerank_top_k: settings.rerank_top_k,
};
```

- [ ] **Step 4: Update settings API types and endpoints**

In `backend/app/api/settings.py`, update `SettingsResponse` and `SettingsUpdate`:

```python
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
```

Update `_build_response` to include new fields:

```python
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
    )
```

Update `update_settings` handler to handle new fields:

```python
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

    _save_overrides(settings)
    return _build_response()
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/components/SettingsPanel.tsx backend/app/api/settings.py
git commit -m "feat: add hybrid search settings UI and API support"
```

---

## Verification

After all tasks are complete:

1. **Settings persistence:** Restart the backend, change settings via UI, restart again — values should persist.
2. **File upload security:** Try uploading a file > 50MB (should get 413), a `.exe` file (should get 400), and a file with special characters in the name (should be sanitized).
3. **Hybrid search:** Upload a document, ask a question that matches by keyword — BM25 should contribute results. Toggle hybrid search off in settings and verify pure vector mode still works.
