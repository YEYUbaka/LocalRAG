"""Behavior tests for the feature-flagged unified retrieval pipeline."""

from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.core import bm25_search as bm25_module
from app.core import vectorstore
from app.domain.tenant import TenantScope


SCOPE = TenantScope(user_id=7, kb_id=11)


@pytest.fixture(autouse=True)
def _restore_retrieval_settings(monkeypatch):
    monkeypatch.setattr(settings, "hybrid_search", True)
    monkeypatch.setattr(settings, "bm25_weight", 0.5)
    monkeypatch.setattr(settings, "retrieval_top_k", 20)
    monkeypatch.setattr(settings, "rerank_top_k", 20)
    monkeypatch.setattr(settings, "rerank_enabled", True)
    monkeypatch.setattr(settings, "rerank_threshold", 0.0)
    monkeypatch.setattr(settings, "similarity_threshold", 0.7)
    monkeypatch.setattr(settings, "post_fusion_similarity_filter_enabled", False, raising=False)


def _item(chunk_id: str, *, distance=None, text=None) -> dict:
    item = {
        "id": chunk_id,
        "document": text or chunk_id,
        "metadata": {"chunk_id": chunk_id, "filename": f"{chunk_id}.md"},
    }
    if distance is not None:
        item["distance"] = distance
    return item


def test_vector_search_can_explicitly_bypass_legacy_similarity_filter(monkeypatch):
    collection = MagicMock()
    collection.count.return_value = 1
    collection.query.return_value = {
        "ids": [["far"]],
        "documents": [["far text"]],
        "metadatas": [[{"chunk_id": "far"}]],
        "distances": [[0.8]],
    }
    monkeypatch.setattr(vectorstore, "get_collection", lambda: collection)
    monkeypatch.setattr(vectorstore, "embed_texts", lambda texts: [[0.1]])

    assert vectorstore.vector_search(SCOPE, "q") == []
    raw = vectorstore.vector_search(
        SCOPE,
        "q",
        apply_similarity_threshold=False,
    )

    assert [item["id"] for item in raw] == ["far"]


def test_unified_search_keeps_bm25_only_deduplicates_and_reranks_once(monkeypatch):
    vector_calls = []
    rerank_calls = []

    def raw_vector(scope, query, top_k=None, apply_similarity_threshold=True):
        vector_calls.append((query, apply_similarity_threshold))
        if query == "原问题":
            return [_item("shared", distance=0.3), _item("dense-original", distance=0.2)]
        return [_item("shared", distance=0.1), _item("dense-variant", distance=0.25)]

    def sparse(scope, query, top_k=20):
        if query == "原问题":
            return [_item("bm25-only"), _item("shared")]
        return [_item("shared")]

    def fake_rerank(query, documents):
        rerank_calls.append((query, list(documents)))
        return [float(len(documents) - index) for index in range(len(documents))]

    monkeypatch.setattr(vectorstore, "vector_search", raw_vector)
    monkeypatch.setattr(bm25_module, "bm25_search", sparse)
    monkeypatch.setattr("app.core.reranker.rerank", fake_rerank)

    results = vectorstore.unified_search(SCOPE, "原问题", ["原问题", "改写"])

    assert vector_calls == [("原问题", False), ("改写", False)]
    assert len(rerank_calls) == 1
    assert rerank_calls[0][0] == "原问题"
    assert {item["id"] for item in results} == {
        "shared",
        "dense-original",
        "dense-variant",
        "bm25-only",
    }
    shared = next(item for item in results if item["id"] == "shared")
    assert shared["distance"] == 0.1
    assert sum(item["id"] == "shared" for item in results) == 1


def test_unified_search_post_filter_keeps_bm25_only(monkeypatch):
    monkeypatch.setattr(settings, "rerank_enabled", False)
    monkeypatch.setattr(settings, "post_fusion_similarity_filter_enabled", True, raising=False)
    monkeypatch.setattr(
        vectorstore,
        "vector_search",
        lambda *args, **kwargs: [_item("far-dense", distance=0.8)],
    )
    monkeypatch.setattr(
        bm25_module,
        "bm25_search",
        lambda *args, **kwargs: [_item("bm25-only")],
    )

    results = vectorstore.unified_search(SCOPE, "原问题", ["原问题"])

    assert [item["id"] for item in results] == ["bm25-only"]


def test_bm25_rebuild_uses_document_stable_chunk_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "unified_fusion_enabled", True)
    file_path = tmp_path / "doc.md"
    file_path.write_text("稳定段落", encoding="utf-8")
    doc = MagicMock(
        id=3,
        status="completed",
        parsed_content="稳定段落",
        file_path=str(file_path),
        filename="doc.md",
        user_id=7,
        kb_id=11,
        document_key="stable-key",
        document_version=2,
        chunker_version="3",
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [doc]
    monkeypatch.setattr("app.services.document_service.parse_document", lambda path: [MagicMock()])
    monkeypatch.setattr(
        "app.services.document_service.split_documents",
        lambda raw, filename: (["稳定段落"], [{"filename": filename}]),
    )
    bm25_module._chunk_store.clear()
    bm25_module._metadata_store.clear()
    bm25_module._owner_map.clear()

    bm25_module.rebuild_from_db(lambda: db)

    assert bm25_module._metadata_store[3][0]["chunk_id"] == "stable-key-v2-c3-000000"
    db.close.assert_called_once_with()
