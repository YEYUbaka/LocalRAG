"""Test query rewrite prompt building."""

from app.core.prompts import build_rewrite_prompt, format_context, build_rag_prompt


def test_build_rewrite_prompt():
    prompt = build_rewrite_prompt("RAG 有什么优势？")
    assert "RAG 有什么优势？" in prompt
    assert "改写" in prompt
    assert "每行一个" in prompt


def test_build_rewrite_prompt_english():
    prompt = build_rewrite_prompt("What is RAG?")
    assert "What is RAG?" in prompt
    assert "改写" in prompt


def test_format_context():
    sources = [
        {
            "document": "这是第一段内容",
            "metadata": {"filename": "doc1.pdf", "page": 1},
        },
        {
            "document": "这是第二段内容",
            "metadata": {"filename": "doc2.txt"},
        },
    ]
    result = format_context(sources)
    assert "来源1" in result
    assert "来源2" in result
    assert "doc1.pdf" in result
    assert "第1页" in result
    assert "doc2.txt" in result
    assert "这是第一段内容" in result
    assert "这是第二段内容" in result


def test_build_rag_prompt_with_sources():
    sources = [
        {
            "document": "some content",
            "metadata": {"filename": "test.pdf", "page": 1},
        },
    ]
    prompt = build_rag_prompt("question", sources)
    assert "知识库" in prompt
    assert "some content" in prompt


def test_build_rag_prompt_without_sources():
    prompt = build_rag_prompt("随便聊聊", [])
    # When no sources, uses general prompt (not the RAG system prompt)
    assert "智能助手" in prompt
    assert "检索到的相关知识库内容" not in prompt
