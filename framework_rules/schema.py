"""Decisão do juiz guiado por regras."""

from __future__ import annotations

from dataclasses import dataclass, field


class JudgeSchemaError(ValueError):
    pass


@dataclass(frozen=True)
class JudgeDecision:
    correto: str            # "Sim" | "Não"
    regras: list[str] = field(default_factory=list)
    sugestao: str = ""

    def __post_init__(self) -> None:
        if self.correto not in {"Sim", "Não"}:
            raise JudgeSchemaError(
                f"'correto' deve ser 'Sim' ou 'Não', veio {self.correto!r}."
            )
