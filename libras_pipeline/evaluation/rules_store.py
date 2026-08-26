"""Carrega a base de regras final (etapa 2: libras_pipeline/simplification/
output/voice2sign_final.csv) e a renderiza num bloco de texto injetável no
prompt do juiz — mesma filosofia de framework_rules/rules_store.py, adaptada
ao schema novo (id/categoria/titulo/descricao/gatilho/exemplos/fontes em vez
de id/categoria/titulo/descricao/verificavel_por_texto/exemplos).

A base cresce sozinha: novas linhas em voice2sign_final.csv aparecem
automaticamente no prompt, sem tocar aqui.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

RULES_PATH = Path(__file__).parents[1] / "simplification" / "output" / "voice2sign_final.csv"


@dataclass(frozen=True)
class Rule:
    id: str
    categoria: str
    titulo: str
    descricao: str
    gatilho: str
    exemplos: list[str] = field(default_factory=list)


def load_rules(path: Path = RULES_PATH) -> list[Rule]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    rules: list[Rule] = []
    for r in rows:
        rules.append(
            Rule(
                id=r["id"],
                categoria=r.get("categoria", ""),
                titulo=r.get("titulo", ""),
                descricao=" ".join(r.get("descricao", "").split()),
                gatilho=r.get("gatilho", ""),
                exemplos=[e.strip() for e in r.get("exemplos", "").split(";") if e.strip()],
            )
        )
    return rules


def render_rules(rules: list[Rule]) -> str:
    """Bloco de texto legível pro modelo, uma regra por item, com ID pra citar."""
    blocks: list[str] = []
    for rule in rules:
        lines = [
            f"[{rule.id}] {rule.titulo}  ({rule.categoria})",
            f"  {rule.descricao}",
            f"  gatilho: {rule.gatilho}",
        ]
        if rule.exemplos:
            lines.append("  exemplos: " + " ; ".join(rule.exemplos[:3]))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def load_rules_text(path: Path = RULES_PATH) -> str:
    return render_rules(load_rules(path))


def valid_rule_ids(path: Path = RULES_PATH) -> set[str]:
    return {rule.id for rule in load_rules(path)}
