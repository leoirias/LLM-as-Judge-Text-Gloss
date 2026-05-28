from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class JudgeSchemaError(ValueError):
    pass


@dataclass(frozen=True)
class JudgeDecision:
    has_error: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.has_error, bool):
            raise JudgeSchemaError("Field 'has_error' must be a boolean.")

        normalized_reason = None if self.reason is None else self.reason.strip()

        if self.has_error and not normalized_reason:
            raise JudgeSchemaError("Field 'reason' is required when 'has_error' is true.")

        object.__setattr__(self, "reason", normalized_reason)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JudgeDecision:
        if "has_error" not in data:
            raise JudgeSchemaError("Missing required field 'has_error'.")

        return cls(
            has_error=data["has_error"],
            reason=data.get("reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        output: dict[str, Any] = {"has_error": self.has_error}

        if self.has_error:
            output["reason"] = self.reason

        return output
