from dataclasses import dataclass
from math import isfinite


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _validate_optional_span(char_start: int | None, char_end: int | None) -> None:
    if (char_start is None) != (char_end is None):
        raise ValueError("character span must include both start and end")
    if char_start is not None and (char_start < 0 or char_end < char_start):
        raise ValueError("character span must be non-negative and ordered")


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    chunk_id: str
    parent_id: str | None
    block_ids: tuple[str, ...]
    text: str
    ordinal: int
    page_index: int | None

    def __post_init__(self) -> None:
        _require_non_empty(self.chunk_id, "chunk_id")
        if self.parent_id is not None:
            _require_non_empty(self.parent_id, "parent_id")
        if not self.block_ids or any(
            not isinstance(block_id, str) or not block_id.strip()
            for block_id in self.block_ids
        ):
            raise ValueError("block_ids must contain non-empty identifiers")
        if self.ordinal < 0:
            raise ValueError("ordinal must be non-negative")
        if self.page_index is not None and self.page_index < 0:
            raise ValueError("page_index must be non-negative")


@dataclass(frozen=True, slots=True)
class ChunkProvenance:
    document_key: str
    document_version: int
    block_ids: tuple[str, ...]
    page_indexes: tuple[int, ...]
    char_start: int | None
    char_end: int | None
    parent_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.document_key, "document_key")
        if self.document_version <= 0:
            raise ValueError("document_version must be positive")
        if not self.block_ids or any(
            not isinstance(block_id, str) or not block_id.strip()
            for block_id in self.block_ids
        ):
            raise ValueError("block_ids must contain non-empty identifiers")
        if any(page_index < 0 for page_index in self.page_indexes):
            raise ValueError("page_indexes must be non-negative")
        if self.parent_id is not None:
            _require_non_empty(self.parent_id, "parent_id")
        _validate_optional_span(self.char_start, self.char_end)


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    chunk_id: str
    dense_score: float | None
    sparse_score: float | None
    fusion_score: float
    rerank_score: float | None
    provenance: ChunkProvenance

    def __post_init__(self) -> None:
        _require_non_empty(self.chunk_id, "chunk_id")
        for field_name, score in (
            ("dense_score", self.dense_score),
            ("sparse_score", self.sparse_score),
            ("fusion_score", self.fusion_score),
            ("rerank_score", self.rerank_score),
        ):
            if score is not None and not isfinite(score):
                raise ValueError(f"{field_name} must be finite")
