"""Retrieval tenant-scope isolation tests.

Verifies that the retrieval layer (vector/BM25) filters by owner_id AND
kb_id so cross-user chunks never surface.
"""

import pytest

from app.domain.tenant import TenantScope
from app.core import vectorstore
from app.core import bm25_search as bm25


def test_vector_search_where_filter_includes_owner(monkeypatch):
    captured = {}

    class _FakeCollection:
        def count(self):
            return 10

        def query(self, **kwargs):
            captured.update(kwargs)
            return {
                "ids": [["doc_1_chunk_0"]],
                "documents": [["内容A"]],
                "metadatas": [[{"owner_id": 1, "kb_id": 1, "doc_id": 1}]],
                "distances": [[0.2]],
            }

    monkeypatch.setattr(vectorstore, "get_collection", lambda: _FakeCollection())
    monkeypatch.setattr(vectorstore, "embed_texts", lambda texts: [[0.1] * 8])

    scope = TenantScope(user_id=1, kb_id=1)
    results = vectorstore.vector_search(scope, "问题", top_k=5)

    where = captured["where"]
    assert "$and" in where
    assert {"owner_id": 1} in where["$and"]
    assert {"kb_id": 1} in where["$and"]
    assert results[0]["metadata"]["owner_id"] == 1


def test_vector_search_scope_b_cannot_see_a(monkeypatch):
    class _FakeCollection:
        def count(self):
            return 10

        def query(self, **kwargs):
            # A's chunk would only be returned if B's scope leaked into the filter
            where = kwargs.get("where")
            assert where is not None
            assert {"owner_id": 2} in where["$and"]
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    monkeypatch.setattr(vectorstore, "get_collection", lambda: _FakeCollection())
    monkeypatch.setattr(vectorstore, "embed_texts", lambda texts: [[0.1] * 8])

    scope_b = TenantScope(user_id=2, kb_id=1)
    results = vectorstore.vector_search(scope_b, "问题", top_k=5)
    assert results == []


def test_bm25_search_filters_by_owner_scope(monkeypatch):
    """BM25 must never return another owner's chunks."""
    corpus = [
        (1, "A 的私有文档内容", {"owner_id": 1, "kb_id": 1, "doc_id": 1}),
        (2, "B 的私有文档内容", {"owner_id": 2, "kb_id": 1, "doc_id": 2}),
    ]

    class _FakeIndex:
        def get_scores(self, tokens):
            return [1.0, 1.0]

    monkeypatch.setattr(bm25, "_corpus", corpus)
    monkeypatch.setattr(bm25, "_bm25_index", _FakeIndex())
    monkeypatch.setattr(bm25, "_dirty", False)
    monkeypatch.setattr(bm25, "_tokenize", lambda text: [text])

    scope_b = TenantScope(user_id=2, kb_id=1)
    results = bm25.bm25_search(scope_b, "B 的私有文档内容", top_k=10)
    assert all(r.get("metadata", {}).get("owner_id") == 2 for r in results)
