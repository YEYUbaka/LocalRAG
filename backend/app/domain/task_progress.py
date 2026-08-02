from dataclasses import dataclass
from enum import StrEnum


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class TaskProgress:
    id: int
    kind: str
    status: TaskStatus
    stage: str
    completed: int
    total: int | None
    percent: int | None
    attempt: int
    message: str | None
    error_code: str | None

    def __post_init__(self) -> None:
        if self.completed < 0 or (self.total is not None and self.total < self.completed):
            raise ValueError("task progress counters are invalid")
        if self.percent is not None and not 0 <= self.percent <= 100:
            raise ValueError("percent must be between 0 and 100")
        if self.attempt < 0:
            raise ValueError("attempt must be non-negative")
