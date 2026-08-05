"""Schemas da extração e da comparação de regras.

ExtractedRule espelha os campos da base da consultoria (asl_rules.yaml) —
id/categoria/titulo/descricao/verificavel_por_texto/exemplos — mais `gatilho`
(condição que ativa a regra) e procedência (fonte_pagina/fonte_citacao), para a
comparação ser maçã-com-maçã. Sem campo de confiança (decisão do usuário).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# status da comparação de UMA regra extraída contra a base da consultoria.
# Slugs ASCII (sem acento) para o modelo emitir exatamente e não errar no parse.
CompareStatus = Literal["ja_temos", "nao_temos", "conflito", "parcial"]


class ExtractedRule(BaseModel):
    id: str                                   # slug, ex.: ASLFD.CAP02.001
    categoria: str                            # morfologia|pronomes|verbos|sintaxe|negacao|...
    titulo: str
    descricao: str                            # o que a regra determina (o "o que fazer")
    gatilho: str                              # condição que ativa a regra (o "quando")
    verificavel_por_texto: bool               # true -> Voice2Sign; false -> Sign2Voice
    exemplos: list[str] = Field(default_factory=list)
    fonte_pagina: int                         # índice [p.N] de onde saiu
    fonte_citacao: str                        # citação verbatim curta (auditável)

    @field_validator("fonte_pagina", mode="before")
    @classmethod
    def _coerce_pagina(cls, v: object) -> int:
        # o modelo às vezes devolve "p.29" / "p. 29" em vez de 29
        if isinstance(v, int):
            return v
        m = re.search(r"\d+", str(v))
        return int(m.group()) if m else -1


class ExtractedRuleSet(BaseModel):
    rules: list[ExtractedRule] = Field(default_factory=list)


class CompareResult(BaseModel):
    status: CompareStatus
    regra_base_correspondente: str = ""       # ID da asl_rules (vazio se nao_temos)
    justificativa: str = ""
