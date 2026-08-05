"""Schema da etapa 2 parte 2: fusão de candidatas duplicadas dentro de uma
categoria, com justificativa e rastreio (`ids_origem`) até as candidatas da
etapa 1 que originaram cada regra final.
"""

from __future__ import annotations

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
