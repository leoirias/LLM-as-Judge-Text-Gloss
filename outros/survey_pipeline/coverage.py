"""Interpret / cobertura (etapa 5 do survey).

Consolida o resultado determinístico + o do LLM num veredito final de 3 estados,
com a origem da decisão. Regra de precedência:

  1. se um check DURO falhou  -> invalido (determinístico; nem chama o LLM)
  2. senão, vale o veredito do LLM (valido | invalido | nao_coberto)

`nao_coberto` = abstenção por falta de cobertura de regra (NÃO por expressão facial).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FinalDecision:
    estado: str                       # valido | invalido | nao_coberto
    origem: str                       # deterministico | llm
    regras: list[str] = field(default_factory=list)
    problema: str = ""
    sugestao: str = ""
    representa_sentido: str = ""
    natural_estrutura: str = ""


def consolidate(hard_findings, verdict) -> FinalDecision:
    """hard_findings: lista de checks.Finding com severity HARD (pode ser vazia).
    verdict: schema.JudgeVerdict ou None (None = parse falhou)."""
    if hard_findings:
        return FinalDecision(
            estado="invalido",
            origem="deterministico",
            regras=[f.rule_id for f in hard_findings],
            problema="; ".join(f.message for f in hard_findings),
        )
    if verdict is None:
        # sem check duro e sem veredito parseável -> abstém (honesto)
        return FinalDecision(estado="nao_coberto", origem="llm",
                             problema="resposta do juiz não parseável")
    return FinalDecision(
        estado=verdict.veredito,
        origem="llm",
        regras=list(verdict.regras),
        problema=verdict.problema,
        sugestao=verdict.sugestao,
        representa_sentido=verdict.representa_sentido,
        natural_estrutura=verdict.natural_estrutura,
    )
