"""Tests for BM25 search and RRF fusion (hybrid retrieval pipeline)."""

import pytest

from app.core.vectorstore import rrf_fusion
from app.core import bm25_search as bm25_module
from app.core.bm25_search import add_document_chunks, remove_document, bm25_search


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_bm25_state():
    """Clear global BM25 state before and after each test."""
    bm25_module._chunk_store.clear()
    bm25_module._metadata_store.clear()
    bm25_module._kb_map.clear()
    bm25_module._bm25_index = None
    bm25_module._corpus = []
    bm25_module._dirty = True
    yield
    bm25_module._chunk_store.clear()
    bm25_module._metadata_store.clear()
    bm25_module._kb_map.clear()
    bm25_module._bm25_index = None
    bm25_module._corpus = []
    bm25_module._dirty = True


# ===========================================================================
# rrf_fusion tests
# ===========================================================================

class TestRrfFusion:
    """Tests for rrf_fusion in vectorstore.py."""

    def test_rrf_fusion_merges_results(self):
        """doc_2 appears in BOTH lists → should rank first after fusion."""
        vector_results = [
            {"id": "doc_1", "document": "vec chunk 1", "metadata": {"doc_id": 1}},
            {"id": "doc_2", "document": "vec chunk 2", "metadata": {"doc_id": 2}},
        ]
        bm25_results = [
            {"id": "doc_3", "document": "bm25 chunk 3", "metadata": {"doc_id": 3}, "doc_id": 3},
            {"id": "doc_2", "document": "bm25 chunk 2", "metadata": {"doc_id": 2}, "doc_id": 2},
        ]

        fused = rrf_fusion(vector_results, bm25_results, top_n=5)

        assert len(fused) == 3
        # doc_2 appears in both → highest combined score → first
        assert fused[0]["id"] == "doc_2"

    def test_rrf_fusion_respects_top_n(self):
        """top_n limits the number of returned results."""
        vector_results = [
            {"id": f"doc_{i}", "document": f"chunk {i}", "metadata": {"doc_id": i}}
            for i in range(10)
        ]
        bm25_results: list[dict] = []

        fused = rrf_fusion(vector_results, bm25_results, top_n=3)

        assert len(fused) == 3

    def test_rrf_fusion_empty_inputs(self):
        """Both empty lists → empty result."""
        assert rrf_fusion([], []) == []

    def test_rrf_fusion_single_empty(self):
        """One side empty → still returns results from the other side."""
        vector_results = [
            {"id": "doc_1", "document": "chunk 1", "metadata": {"doc_id": 1}},
        ]
        fused = rrf_fusion(vector_results, [], top_n=5)
        assert len(fused) == 1
        assert fused[0]["id"] == "doc_1"

    def test_rrf_fusion_weight_bias(self):
        """Higher bm25_weight should push bm25-only docs above vector-only docs."""
        # doc_V is rank 0 in vector, absent from BM25
        # doc_B is rank 0 in BM25, absent from vector
        vector_results = [
            {"id": "doc_V", "document": "vector only", "metadata": {"doc_id": 10}},
        ]
        bm25_results = [
            {"id": "doc_B", "document": "bm25 only", "metadata": {"doc_id": 20}, "doc_id": 20},
        ]

        # Equal weights → vector rank-0 gets same weight as bm25 rank-0
        fused_equal = rrf_fusion(vector_results, bm25_results, vector_weight=0.5, bm25_weight=0.5, top_n=5)
        assert len(fused_equal) == 2
        # With equal weights and equal rank, order is deterministic by insertion
        # (both get 0.5/60), Python's sorted is stable so vector comes first
        assert fused_equal[0]["id"] == "doc_V"

        # Bias heavily toward BM25
        fused_biased = rrf_fusion(vector_results, bm25_results, vector_weight=0.1, bm25_weight=0.9, top_n=5)
        assert len(fused_biased) == 2
        # doc_B (bm25 rank-0) now has 0.9/60 > 0.1/60 → should be first
        assert fused_biased[0]["id"] == "doc_B"


# ===========================================================================
# bm25_search tests
# ===========================================================================

class TestBm25Search:
    """Tests for bm25 keyword search in bm25_search.py."""

    def test_bm25_add_and_search(self):
        """Adding documents then searching returns matching results with correct metadata."""
        # Need >= 3 docs so BM25 IDF is non-zero for terms appearing in 1 doc
        add_document_chunks(
            doc_id=1,
            chunks=["Python 是一种广泛使用的编程语言", "Java 也是一种流行的编程语言"],
            kb_id=1,
            metadatas=[{"source": "python.md"}, {"source": "java.md"}],
        )
        add_document_chunks(
            doc_id=2,
            chunks=["机器学习是人工智能的一个子领域"],
            kb_id=1,
            metadatas=[{"source": "ml.md"}],
        )
        add_document_chunks(
            doc_id=3,
            chunks=["操作系统负责管理计算机的硬件资源"],
            kb_id=1,
            metadatas=[{"source": "os.md"}],
        )

        results = bm25_search("Python 编程", top_k=5)

        assert len(results) > 0
        # The first result should be about Python
        top = results[0]
        assert "Python" in top["document"]
        assert top["doc_id"] == 1
        assert top["metadata"]["source"] == "python.md"
        assert "id" in top
        assert top["bm25_score"] > 0

    def test_bm25_remove_document(self):
        """After removing a document, its chunks no longer appear in search results."""
        # Need >= 3 docs so BM25 IDF is non-zero
        add_document_chunks(
            doc_id=1,
            chunks=["深度学习使用神经网络进行特征提取"],
            kb_id=1,
        )
        add_document_chunks(
            doc_id=2,
            chunks=["自然语言处理是人工智能的重要分支"],
            kb_id=1,
        )
        add_document_chunks(
            doc_id=3,
            chunks=["数据库索引可以提高查询性能"],
            kb_id=1,
        )

        # Verify doc 1 is searchable
        results_before = bm25_search("深度学习", top_k=10)
        doc_ids_before = {r["doc_id"] for r in results_before}
        assert 1 in doc_ids_before

        # Remove doc 1
        remove_document(1)

        results_after = bm25_search("深度学习 神经网络", top_k=10)
        doc_ids_after = {r["doc_id"] for r in results_after}
        assert 1 not in doc_ids_after

    def test_bm25_search_with_kb_filter(self):
        """kb_id filter returns only results from the specified knowledge base."""
        # Use distinct content per kb so BM25 IDF is non-zero
        add_document_chunks(
            doc_id=1,
            chunks=["Python 编程语言的列表推导式非常简洁"],
            kb_id=1,
        )
        add_document_chunks(
            doc_id=2,
            chunks=["Java 的泛型机制提供了类型安全"],
            kb_id=2,
        )
        add_document_chunks(
            doc_id=3,
            chunks=["Go 语言的协程模型适合高并发"],
            kb_id=3,
        )

        results_kb1 = bm25_search("Python 编程", top_k=10, kb_id=1)
        results_kb2 = bm25_search("Java 泛型", top_k=10, kb_id=2)

        assert len(results_kb1) > 0
        assert len(results_kb2) > 0
        assert all(r["doc_id"] == 1 for r in results_kb1)
        assert all(r["doc_id"] == 2 for r in results_kb2)

    def test_bm25_search_empty_index(self):
        """Searching an empty index returns an empty list."""
        results = bm25_search("任何查询", top_k=5)
        assert results == []
