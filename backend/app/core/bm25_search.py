"""BM25 keyword search index for hybrid retrieval."""

import logging
import os
from rank_bm25 import BM25Okapi

from app.domain.tenant import TenantScope

# 静默 jieba 的字典加载输出
with open(os.devnull, "w") as _devnull:
    import sys
    _old_stdout = sys.stdout
    sys.stdout = _devnull
    import jieba
    sys.stdout = _old_stdout

logger = logging.getLogger(__name__)

# doc_id -> list of chunk texts
_chunk_store: dict[int, list[str]] = {}
# doc_id -> list of chunk metadata
_metadata_store: dict[int, list[dict]] = {}
# doc_id -> (owner_id, kb_id)
_owner_map: dict[int, tuple[int, int]] = {}
_bm25_index: BM25Okapi | None = None
_corpus: list[tuple[int, str, dict]] = []  # [(doc_id, chunk_text, metadata), ...]
_dirty = True


def _tokenize(text: str) -> list[str]:
    """Tokenize Chinese text using jieba."""
    return list(jieba.cut(text))


def _rebuild_index() -> None:
    """Rebuild the BM25 index from all stored chunks."""
    global _bm25_index, _corpus, _dirty
    _corpus = []
    for doc_id, chunks in _chunk_store.items():
        metas = _metadata_store.get(doc_id, [{}] * len(chunks))
        for i, chunk in enumerate(chunks):
            meta = metas[i] if i < len(metas) else {}
            _corpus.append((doc_id, chunk, meta))

    if not _corpus:
        _bm25_index = None
        _dirty = False
        return

    tokenized = [_tokenize(text) for _, text, _ in _corpus]
    _bm25_index = BM25Okapi(tokenized)
    _dirty = False
    logger.info(f"BM25 index rebuilt: {len(_corpus)} chunks from {len(_chunk_store)} documents")


def add_document_chunks(scope: TenantScope, document_id: int, chunks: list[str], metadatas: list[dict] | None = None) -> None:
    """Add chunks for a document to the BM25 index."""
    global _dirty
    try:
        enriched = []
        for i, meta in enumerate(metadatas or [{}] * len(chunks)):
            enriched.append({
                **meta,
                "chunk_id": meta.get("chunk_id", f"doc_{document_id}_chunk_{i}"),
                "owner_id": scope.user_id,
                "kb_id": scope.kb_id,
                "doc_id": document_id,
            })
        _chunk_store[document_id] = chunks
        _metadata_store[document_id] = enriched
        _owner_map[document_id] = (scope.user_id, scope.kb_id)
        _dirty = True
    except Exception as e:
        logger.warning(f"BM25: failed to add chunks for doc {document_id}: {e}")


def remove_document(document_id: int) -> None:
    """Remove a document's chunks from the BM25 index."""
    global _dirty
    try:
        if document_id in _chunk_store:
            del _chunk_store[document_id]
            _dirty = True
        _metadata_store.pop(document_id, None)
        _owner_map.pop(document_id, None)
    except Exception as e:
        logger.warning(f"BM25: failed to remove doc {document_id}: {e}")


def bm25_search(scope: TenantScope, query: str, top_k: int = 20) -> list[dict]:
    """Search using BM25 keyword matching, scoped to owner + knowledge base."""
    global _dirty
    if _dirty:
        _rebuild_index()

    if _bm25_index is None or not _corpus:
        return []

    tokenized_query = _tokenize(query)
    scores = _bm25_index.get_scores(tokenized_query)

    # Get top-k indices by score, filtered by tenant scope
    ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

    results = []
    for idx in ranked_indices:
        if scores[idx] <= 0:
            continue
        doc_id, text, meta = _corpus[idx]
        owner, kb_id = _owner_map.get(doc_id, (None, None))
        if owner != scope.user_id or kb_id != scope.kb_id:
            continue
        results.append({
            "id": meta.get("chunk_id", f"doc_{doc_id}_chunk_{idx}"),
            "document": text,
            "doc_id": doc_id,
            "bm25_score": float(scores[idx]),
            "metadata": meta,
        })
        if len(results) >= top_k:
            break

    return results


def rebuild_from_db(db_session_factory) -> None:
    """Rebuild BM25 index from all completed documents in the database."""
    from app.models import Document
    db = db_session_factory()
    try:
        docs = db.query(Document).filter(Document.status == "completed").all()
        for doc in docs:
            if doc.parsed_content:
                from app.services.document_service import split_documents, parse_document
                from pathlib import Path
                try:
                    file_path = Path(doc.file_path)
                    if file_path.exists():
                        raw_docs = parse_document(file_path)
                        texts, metadatas = split_documents(raw_docs, doc.filename)
                        scope = TenantScope(user_id=doc.user_id or 1, kb_id=doc.kb_id or 1)
                        add_document_chunks(scope, doc.id, texts, metadatas=metadatas)
                except Exception as e:
                    logger.warning(f"BM25: failed to rebuild for doc {doc.id}: {e}")
        _rebuild_index()
        logger.info(f"BM25 index rebuilt from DB: {len(_chunk_store)} documents")
    finally:
        db.close()
