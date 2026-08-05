"""Schema da etapa 1 (extração): doc -> regras candidatas em JSON.

`categoria` já vem do modelo (lista fechada em config.yaml/prompt) pra
facilitar a etapa 2 (simplificação/agrupamento) mais tarde. `id`, porém, é
ATRIBUÍDO PELO CÓDIGO em extract.py (sequencial por categoria, ex.:
ASLFD.VERBOS.003) — não é pedido ao modelo, porque cada janela de página é
uma chamada de LLM independente, sem memória das IDs já usadas nas janelas
anteriores; deixar o modelo inventar IDs geraria colisão. `fonte_livro`
também é preenchido pelo código (rótulo do livro em config.yaml).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


class ExtractedRule(BaseModel):
    categoria: str                            # da lista fechada (ver config.yaml)
    titulo: str
    descricao: str                            # o que a regra determina (o "o que fazer")
    gatilho: str                              # condição que ativa a regra (o "quando")
    verificavel_por_texto: bool               # true -> dá pra checar só no texto da glosa
    exemplos: list[str] = Field(default_factory=list)
    fonte_pagina: int                         # índice [p.N] de onde saiu
    fonte_citacao: str                        # citação verbatim curta (auditável)

    id: str = ""                              # preenchido por extract.py
    fonte_livro: str = ""                     # preenchido por extract.py

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
