from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class JudgeSchemaError(ValueError):
    pass


_C_TO_LABEL = {1: "wrong", 2: "partial", 3: "correct"}
_VALID_LABELS = set(_C_TO_LABEL.values())


@dataclass(frozen=True)
class JudgeDecision:
    classification: str  # wrong | partial | correct
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.classification not in _VALID_LABELS:
            raise JudgeSchemaError(
                f"Invalid classification {self.classification!r}. "
                f"Expected one of: {sorted(_VALID_LABELS)}"
            )

    @property
    def has_error(self) -> bool:
        return self.classification == "wrong"

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_error": self.has_error,
            "classification": self.classification,
            "reason": self.reason,
        }
