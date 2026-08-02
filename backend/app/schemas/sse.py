from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SSE_SCHEMA_VERSION = 1


class SSEBaseV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = SSE_SCHEMA_VERSION


class SourceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    file: str
    page: int | None = None
    snippet: str
    doc_id: int | None = None
    type: Literal["document", "web"] = "document"
    url: str | None = None


class TokenEventV1(SSEBaseV1):
    content: str


class SourcesEventV1(SSEBaseV1):
    sources: tuple[SourceV1, ...]


class DoneEventV1(SSEBaseV1):
    conversation_id: int = Field(gt=0)


class ErrorEventV1(SSEBaseV1):
    message: str


class ThinkingEventV1(SSEBaseV1):
    status: Literal["started", "analyzing", "reasoning", "completed"]
    message: str
