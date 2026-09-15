from dataclasses import dataclass
from enum import StrEnum
import re
import unicodedata
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CLASSIFICATION_VERSION = "1"
PROMPT_VERSION = "1"

TOP_CATEGORY_NAMES = (
    "工作与项目",
    "技术与工具",
    "学习与研究",
    "财务与法律",
    "健康与生活",
    "兴趣与收藏",
    "其他",
)

TOP_CATEGORY_DESCRIPTIONS = {
    "工作与项目": "工作职责、项目资料、会议、计划与交付",
    "技术与工具": "软件、编程、系统、设备与工具使用",
    "学习与研究": "课程、论文、读书、知识与研究资料",
    "财务与法律": "账务、投资、合同、税务与法律资料",
    "健康与生活": "健康、家庭、日常生活与个人事务",
    "兴趣与收藏": "兴趣爱好、娱乐、旅行与收藏",
    "其他": "无法稳定归入以上分类的资料",
}

_CATEGORY_SEPARATORS = ("/", "\\", ">", "→", "›", "::", "\r", "\n")


class ClassificationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FALLBACK = "fallback"
    FAILED = "failed"


class ClassificationMethod(StrEnum):
    LLM = "llm"
    EMBEDDING = "embedding"
    USER = "user"
    NONE = "none"


@dataclass(frozen=True)
class RetrievalScope:
    user_id: int
    kb_id: int | None = None
    document_ids: frozenset[int] | None = None

    def __post_init__(self) -> None:
        if self.user_id <= 0:
            raise ValueError("RetrievalScope user_id must be positive")
        if self.kb_id is not None and self.kb_id <= 0:
            raise ValueError("RetrievalScope kb_id must be positive")
        if self.document_ids is not None and any(
            document_id <= 0 for document_id in self.document_ids
        ):
            raise ValueError("RetrievalScope document_ids must be positive")


def normalize_tag(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"\s+", " ", normalized)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class CategoryOption(_FrozenModel):
    path: str = Field(min_length=1, max_length=220)
    description: str = Field(default="", max_length=500)


class ClassificationPacket(_FrozenModel):
    filename: str = Field(min_length=1, max_length=255)
    extension: str = Field(default="", max_length=16)
    headings: tuple[str, ...] = Field(default=(), max_length=50)
    snippets: tuple[str, ...] = Field(min_length=1, max_length=8)
    category_options: tuple[CategoryOption, ...] = Field(min_length=7)
    common_tags: tuple[str, ...] = Field(default=(), max_length=50)


class _ClassificationResult(_FrozenModel):
    top_category: str
    subcategory: str | None

    @field_validator("top_category")
    @classmethod
    def validate_top_category(cls, value: str) -> str:
        if value not in TOP_CATEGORY_NAMES:
            raise ValueError("top_category must be a fixed top category")
        return value

    @field_validator("subcategory")
    @classmethod
    def validate_subcategory_depth(cls, value: str | None) -> str | None:
        if value is not None and any(separator in value for separator in _CATEGORY_SEPARATORS):
            raise ValueError("subcategory must not contain hierarchy separators")
        return value


class ClassificationDecision(_ClassificationResult):
    create_subcategory: bool
    tags: list[str] = Field(min_length=3, max_length=8)
    summary: str
    confidence: float = Field(ge=0, le=1)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, values: list[str]) -> list[str]:
        normalized = [normalize_tag(value) for value in values]
        if any(not value for value in normalized):
            raise ValueError("tags must not normalize to empty values")
        if len(normalized) != len(set(normalized)):
            raise ValueError("tags must be unique after normalization")
        return values


class ClassificationOutcome(_ClassificationResult):
    method: ClassificationMethod
    subcategory: str | None = None
    create_subcategory: bool = False
    tags: tuple[str, ...] = ()
    summary: str | None = Field(default=None, max_length=500)
    confidence: float | None = Field(default=None, ge=0, le=1)
    error_code: str | None = Field(default=None, max_length=64)
    llm_call_count: int = Field(default=0, ge=0, le=2)

    @model_validator(mode="after")
    def validate_method_invariants(self) -> Self:
        normalized_tags = [normalize_tag(value) for value in self.tags]
        tags_are_valid = (
            3 <= len(self.tags) <= 8
            and all(normalized_tags)
            and len(normalized_tags) == len(set(normalized_tags))
        )

        if self.method is ClassificationMethod.LLM:
            if not tags_are_valid:
                raise ValueError("llm outcome requires 3-8 unique normalized tags")
            if self.summary is None or not self.summary:
                raise ValueError("llm outcome requires a non-empty summary")
            if self.confidence is None:
                raise ValueError("llm outcome requires confidence")
            if not 1 <= self.llm_call_count <= 2:
                raise ValueError("llm outcome requires one or two LLM calls")
        elif self.method is ClassificationMethod.EMBEDDING:
            if self.tags or self.summary is not None:
                raise ValueError("embedding outcome cannot contain generated tags or summary")
            if self.confidence is None:
                raise ValueError("embedding outcome requires confidence")
            if self.create_subcategory:
                raise ValueError("embedding outcome cannot create a subcategory")
        elif self.method is ClassificationMethod.NONE:
            if (
                self.top_category != "其他"
                or self.subcategory is not None
                or self.tags
                or self.summary is not None
                or self.confidence is not None
                or self.create_subcategory
            ):
                raise ValueError("none outcome must be an empty fallback to 其他")
        elif self.method is ClassificationMethod.USER:
            if self.tags or self.summary is not None or self.create_subcategory:
                raise ValueError("user outcome cannot contain automatic metadata")
            if self.llm_call_count != 0:
                raise ValueError("user outcome cannot contain LLM calls")

        return self
