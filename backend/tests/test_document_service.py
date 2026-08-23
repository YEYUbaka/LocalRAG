"""Test document service functions."""

import hashlib
from unittest.mock import MagicMock
from pathlib import Path
import tempfile
import os

from app.services.document_service import (
    CHUNKER_VERSION,
    build_stable_chunk_metadata,
    compute_md5,
    compute_page_breaks,
    parse_document,
)


def test_compute_md5():
    """Test MD5 computation for a file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("hello world")
        f.flush()
        path = Path(f.name)

    try:
        md5 = compute_md5(path)
        assert len(md5) == 32
        assert isinstance(md5, str)
        # MD5 of "hello world" is well-known
        assert md5 == "5eb63bbbe01eeed093cb22bb8f5acdc3"
    finally:
        os.unlink(path)


def test_compute_page_breaks_none_for_non_pdf():
    """Test that page_breaks returns None for non-PDF docs."""
    doc = MagicMock()
    doc.metadata = {"source": "test.txt"}
    result = compute_page_breaks([doc])
    assert result is None


def test_compute_page_breaks_for_pdf():
    """Test page_breaks calculation for PDF documents."""
    doc1 = MagicMock()
    doc1.metadata = {"page": 0}
    doc1.page_content = "a" * 100

    doc2 = MagicMock()
    doc2.metadata = {"page": 0}
    doc2.page_content = "b" * 50

    doc3 = MagicMock()
    doc3.metadata = {"page": 1}
    doc3.page_content = "c" * 80

    result = compute_page_breaks([doc1, doc2, doc3])
    assert result == [0, 150]  # page 0 starts at 0, page 1 starts at 150


def test_compute_page_breaks_empty():
    """Test page_breaks for empty document list."""
    assert compute_page_breaks([]) is None


def test_compute_page_breaks_single_page():
    """Test page_breaks for single-page PDF."""
    doc = MagicMock()
    doc.metadata = {"page": 0}
    doc.page_content = "content"

    result = compute_page_breaks([doc])
    assert result == [0]


def test_build_stable_chunk_metadata_is_deterministic():
    texts = ["第一段", "第二段"]
    source = [{"filename": "示例.md"}, {"filename": "示例.md", "page": 1}]

    first = build_stable_chunk_metadata("abc123", 2, texts, source)
    second = build_stable_chunk_metadata("abc123", 2, texts, source)

    assert first == second
    assert [item["chunk_id"] for item in first] == [
        f"abc123-v2-c{CHUNKER_VERSION}-000000",
        f"abc123-v2-c{CHUNKER_VERSION}-000001",
    ]
    assert first[0]["content_hash"] == hashlib.sha256("第一段".encode("utf-8")).hexdigest()
    assert first[1]["page"] == 1


def test_parse_utf8_csv_table_corpus():
    path = Path(__file__).resolve().parents[2] / "test_docs" / "Linux文本处理三剑客.csv"

    documents = parse_document(path)
    content = "\n".join(document.page_content for document in documents)

    assert "工具: grep" in content
    assert "示例: grep -n 'error' app.log" in content


def test_parse_xlsx_table_corpus_without_unstructured_dependency():
    path = Path(__file__).resolve().parents[2] / "test_docs" / "Git常用命令对照表.xlsx"

    documents = parse_document(path)
    content = "\n".join(document.page_content for document in documents)

    assert {document.metadata["sheet"] for document in documents} == {"基础操作", "分支与远程"}
    assert "命令\t作用\t示例" in content
    assert "git status" in content
