from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantScope:
    user_id: int
    kb_id: int

    def __post_init__(self) -> None:
        if self.user_id <= 0 or self.kb_id <= 0:
            raise ValueError("TenantScope identifiers must be positive")
