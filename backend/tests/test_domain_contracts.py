from dataclasses import FrozenInstanceError
from math import inf

import pytest

from app.domain.canonical import CanonicalBlock, CanonicalDocument
from app.domain.chunking import ChunkProvenance, ChunkRecord, SearchCandidate
from app.domain.tenant import TenantScope
from app.schemas.sse import DoneEventV1, SSE_SCHEMA_VERSION


def test_tenant_scope_is_positive_and_immutable():
    scope = TenantScope(user_id=7, kb_id=11)
    assert (scope.user_id, scope.kb_id) == (7, 11)
    with pytest.raises(FrozenInstanceError):
        scope.user_id = 8
    with pytest.raises(ValueError, match="positive"):
        TenantScope(user_id=0, kb_id=11)


def test_done_event_has_frozen_schema_version():
    event = DoneEventV1(conversation_id=5)
    assert event.model_dump() == {
        "schema_version": SSE_SCHEMA_VERSION,
        "conversation_id": 5,
    }


def make_block(**overrides):
    values = {
        "block_id": "block-000001",
        "block_type": "paragraph",
        "text": "稳定的解析文本",
        "heading_path": ("第一章",),
        "reading_order": 0,
        "page_index": 0,
        "char_start": 0,
        "char_end": 6,
    }
    values.update(overrides)
    return CanonicalBlock(**values)


def test_canonical_document_preserves_ordered_unique_immutable_blocks():
    first = make_block()
    second = make_block(block_id="block-000002", reading_order=1)
    document = CanonicalDocument(
        document_key="document-key",
        content_hash="content-hash",
        parser_name="unstructured",
        parser_version="1.0",
        blocks=(first, second),
    )

    assert document.blocks == (first, second)
    with pytest.raises(FrozenInstanceError):
        document.document_key = "changed"
    with pytest.raises(ValueError, match="unique"):
        CanonicalDocument(
            document_key="document-key",
            content_hash="content-hash",
            parser_name="unstructured",
            parser_version="1.0",
            blocks=(first, first),
        )


def test_canonical_block_normalizes_table_cells_to_an_immutable_snapshot():
    cells = [["状态码", "含义"], ["200", "成功"]]
    block = make_block(table_cells=cells)

    cells[1].append("later mutation")
    assert block.table_cells == (("状态码", "含义"), ("200", "成功"))
    with pytest.raises(AttributeError):
        block.table_cells.append(("404", "未找到"))
    with pytest.raises(FrozenInstanceError):
        block.table_cells = ()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"block_id": ""}, "block_id"),
        ({"reading_order": -1}, "reading_order"),
        ({"page_index": -1}, "page_index"),
        ({"char_start": 7, "char_end": 6}, "character span"),
        ({"char_start": None, "char_end": 6}, "character span"),
        ({"ocr_confidence": 1.1}, "ocr_confidence"),
        ({"ocr_confidence": inf}, "ocr_confidence"),
        ({"bbox": (0.0, 0.0, inf, 1.0)}, "bbox"),
        ({"page_size": (inf, 100.0)}, "page_size"),
    ],
)
def test_canonical_block_rejects_invalid_identity_or_provenance(overrides, message):
    with pytest.raises(ValueError, match=message):
        make_block(**overrides)


def make_provenance(**overrides):
    values = {
        "document_key": "document-key",
        "document_version": 1,
        "block_ids": ("block-000001",),
        "page_indexes": (0,),
        "char_start": 0,
        "char_end": 6,
        "parent_id": "parent-000001",
    }
    values.update(overrides)
    return ChunkProvenance(**values)


def test_chunk_record_keeps_complete_immutable_provenance_and_finite_scores():
    provenance = make_provenance()
    record = ChunkRecord(
        chunk_id="document-key-v1-c1-000000",
        text="可检索的文本",
        ordinal=0,
        provenance=provenance,
    )
    candidate = SearchCandidate(
        chunk_id=record.chunk_id,
        dense_score=0.3,
        sparse_score=None,
        fusion_score=0.8,
        rerank_score=1.2,
        provenance=provenance,
    )

    assert record.provenance == provenance
    assert record.provenance.parent_id == "parent-000001"
    assert record.provenance.block_ids == ("block-000001",)
    assert record.provenance.page_indexes == (0,)
    assert (record.provenance.char_start, record.provenance.char_end) == (0, 6)
    with pytest.raises(FrozenInstanceError):
        record.ordinal = 1
    with pytest.raises(FrozenInstanceError):
        provenance.parent_id = "changed"
    with pytest.raises(FrozenInstanceError):
        candidate.fusion_score = 0.1
    with pytest.raises(ValueError, match="finite"):
        SearchCandidate(
            chunk_id=record.chunk_id,
            dense_score=None,
            sparse_score=None,
            fusion_score=inf,
            rerank_score=None,
            provenance=provenance,
        )


@pytest.mark.parametrize(
    ("factory", "overrides", "message"),
    [
        (
            ChunkRecord,
            {
                "chunk_id": "",
                "text": "text",
                "ordinal": 0,
                "provenance": make_provenance(),
            },
            "chunk_id",
        ),
        (
            ChunkRecord,
            {
                "chunk_id": "chunk",
                "text": "text",
                "ordinal": -1,
                "provenance": make_provenance(),
            },
            "ordinal",
        ),
        (
            ChunkRecord,
            {
                "chunk_id": "chunk",
                "text": "text",
                "ordinal": 0,
                "provenance": "not-a-provenance",
            },
            "provenance",
        ),
        (
            ChunkProvenance,
            {
                "document_key": "",
                "document_version": 1,
                "block_ids": ("block-000001",),
                "page_indexes": (0,),
                "char_start": 0,
                "char_end": 1,
            },
            "document_key",
        ),
        (
            ChunkProvenance,
            {
                "document_key": "document",
                "document_version": 0,
                "block_ids": ("block-000001",),
                "page_indexes": (0,),
                "char_start": 0,
                "char_end": 1,
            },
            "document_version",
        ),
        (
            ChunkProvenance,
            {
                "document_key": "document",
                "document_version": 1,
                "block_ids": ("block-000001",),
                "page_indexes": (-1,),
                "char_start": 0,
                "char_end": 1,
            },
            "page_indexes",
        ),
        (
            ChunkProvenance,
            {
                "document_key": "document",
                "document_version": 1,
                "block_ids": ("block-000001",),
                "page_indexes": (0,),
                "char_start": None,
                "char_end": 1,
            },
            "character span",
        ),
    ],
)
def test_chunk_contracts_reject_invalid_provenance(factory, overrides, message):
    with pytest.raises(ValueError, match=message):
        factory(**overrides)
