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
class CanonicalBlock:
    block_id: str
    block_type: str
    text: str
    heading_path: tuple[str, ...]
    reading_order: int
    page_index: int | None
    char_start: int | None
    char_end: int | None
    bbox: tuple[float, float, float, float] | None = None
    table_cells: list[list[str]] | None = None
    image_caption: str | None = None
    ocr_confidence: float | None = None
    page_size: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.block_id, "block_id")
        _require_non_empty(self.block_type, "block_type")
        if self.reading_order < 0:
            raise ValueError("reading_order must be non-negative")
        if self.page_index is not None and self.page_index < 0:
            raise ValueError("page_index must be non-negative")
        _validate_optional_span(self.char_start, self.char_end)
        if self.bbox is not None:
            if len(self.bbox) != 4 or not all(isfinite(value) for value in self.bbox):
                raise ValueError("bbox must contain four finite coordinates")
        if self.page_size is not None:
            if (
                len(self.page_size) != 2
                or not all(isfinite(value) and value > 0 for value in self.page_size)
            ):
                raise ValueError("page_size must contain two positive finite values")
        if self.ocr_confidence is not None and (
            not isfinite(self.ocr_confidence) or not 0 <= self.ocr_confidence <= 1
        ):
            raise ValueError("ocr_confidence must be finite and between 0 and 1")


@dataclass(frozen=True, slots=True)
class CanonicalDocument:
    document_key: str
    content_hash: str
    parser_name: str
    parser_version: str
    blocks: tuple[CanonicalBlock, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.document_key, "document_key")
        _require_non_empty(self.content_hash, "content_hash")
        _require_non_empty(self.parser_name, "parser_name")
        _require_non_empty(self.parser_version, "parser_version")
        block_ids = tuple(block.block_id for block in self.blocks)
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("CanonicalDocument block_id values must be unique")
