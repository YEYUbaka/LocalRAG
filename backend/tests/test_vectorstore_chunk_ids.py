from unittest.mock import MagicMock

from app.core import vectorstore
from app.domain.tenant import TenantScope


def test_add_documents_upserts_by_canonical_chunk_id(monkeypatch):
    collection = MagicMock()
    monkeypatch.setattr(vectorstore, "get_collection", lambda: collection)
    monkeypatch.setattr(vectorstore, "embed_texts", lambda texts: [[0.1]] * len(texts))
    scope = TenantScope(user_id=7, kb_id=9)
    metadatas = [
        {
            "chunk_id": "doc-key-v1-c1-000000",
            "document_key": "doc-key",
            "document_version": 1,
            "chunker_version": "1",
            "content_hash": "hash",
        }
    ]

    vectorstore.add_documents(scope, 42, ["content"], metadatas)

    collection.upsert.assert_called_once()
    kwargs = collection.upsert.call_args.kwargs
    assert kwargs["ids"] == ["doc-key-v1-c1-000000"]
    assert kwargs["metadatas"][0]["chunk_id"] == "doc-key-v1-c1-000000"
    assert kwargs["metadatas"][0]["owner_id"] == 7
    collection.add.assert_not_called()


def test_add_documents_keeps_legacy_id_fallback(monkeypatch):
    collection = MagicMock()
    monkeypatch.setattr(vectorstore, "get_collection", lambda: collection)
    monkeypatch.setattr(vectorstore, "embed_texts", lambda texts: [[0.1]] * len(texts))

    vectorstore.add_documents(
        TenantScope(user_id=1, kb_id=1),
        5,
        ["legacy"],
        [{"filename": "legacy.txt"}],
    )

    assert collection.upsert.call_args.kwargs["ids"] == ["doc_5_chunk_0"]
