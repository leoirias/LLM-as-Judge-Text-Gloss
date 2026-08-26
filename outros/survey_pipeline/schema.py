"""Veredito do resíduo LLM."""

from __future__ import annotations

from dataclasses import dataclass, field

ESTADOS = {"valido", "invalido", "nao_coberto"}


class VerdictError(ValueError):
    pass


@dataclass(frozen=True)
class JudgeVerdict:
    veredito: str                       # valido | invalido | nao_coberto
    representa_sentido: str = ""         # "Sim" | "Não"
    natural_estrutura: str = ""         # "Sim" | "Não"
    regras: list[str] = field(default_factory=list)
    problema: str = ""
    sugestao: str = ""

    def __post_init__(self) -> None:
        if self.veredito not in ESTADOS:
            raise VerdictError(f"veredito inválido: {self.veredito!r} (esperado {ESTADOS})")
