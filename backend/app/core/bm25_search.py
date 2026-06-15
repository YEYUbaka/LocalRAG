"""BM25 keyword search index for hybrid retrieval."""

import logging
import os
from rank_bm25 import BM25Okapi

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
# doc_id -> kb_id mapping
_kb_map: dict[int, int] = {}
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


def add_document_chunks(doc_id: int, chunks: list[str], kb_id: int = 1) -> None:
    """Add chunks for a document to the BM25 index."""
    global _dirty
    try:
        _chunk_store[doc_id] = chunks
        _kb_map[doc_id] = kb_id
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
        _kb_map.pop(doc_id, None)
    except Exception as e:
        logger.warning(f"BM25: failed to remove doc {doc_id}: {e}")


def bm25_search(query: str, top_k: int = 20, kb_id: int | None = None) -> list[dict]:
    """Search using BM25 keyword matching. Returns list of {id, document, metadata}."""
    global _dirty
    if _dirty:
        _rebuild_index()

    if _bm25_index is None or not _corpus:
        return []

    tokenized_query = _tokenize(query)
    scores = _bm25_index.get_scores(tokenized_query)

    # Get top-k indices by score, filtered by kb_id if specified
    ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

    results = []
    for idx in ranked_indices:
        if scores[idx] <= 0:
            continue
        doc_id, text = _corpus[idx]
        if kb_id is not None and _kb_map.get(doc_id) != kb_id:
            continue
        results.append({
            "id": f"doc_{doc_id}_chunk_{idx}",
            "document": text,
            "doc_id": doc_id,
            "bm25_score": float(scores[idx]),
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
                        texts, _ = split_documents(raw_docs, doc.filename)
                        add_document_chunks(doc.id, texts, kb_id=doc.kb_id)
                except Exception as e:
                    logger.warning(f"BM25: failed to rebuild for doc {doc.id}: {e}")
        _rebuild_index()
        logger.info(f"BM25 index rebuilt from DB: {len(_chunk_store)} documents")
    finally:
        db.close()
