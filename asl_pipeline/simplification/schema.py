"""Schema da etapa 2: parte 2 (fusão de duplicatas dentro de uma categoria,
com justificativa e rastreio `ids_origem` até as candidatas da etapa 1) e
parte 3 sob demanda (comparação de candidatas de uma fonte nova contra a
base já consolidada).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MergedRule(BaseModel):
    titulo: str
    descricao: str
    gatilho: str
    exemplos: list[str] = Field(default_factory=list)
    ids_origem: list[str]              # IDs das candidatas (etapa 1) fundidas nesta regra
    justificativa_fusao: str = ""      # por que foram fundidas; "" se ids_origem tem só 1 item

    # preenchidos pelo código depois da fusão (não pedidos ao modelo)
    id: str = ""
    categoria: str = ""


class MergedRuleSet(BaseModel):
    regras_finais: list[MergedRule] = Field(default_factory=list)


# status da comparação de UMA candidata nova contra a base já consolidada.
# Slugs ASCII (sem acento) pro modelo emitir exatamente e não errar no parse.
CompareStatus = Literal["ja_temos", "nao_temos", "conflito", "parcial"]


class CompareResult(BaseModel):
    status: CompareStatus
    regra_base_correspondente: str = ""    # ID da regra da base (vazio se nao_temos)
    justificativa: str = ""
