"""Carrega a base de regras (rules/asl_rules.yaml) e a renderiza num bloco de
texto injetável no prompt do juiz.

A base cresce sozinha: novas entradas em `asl_rules.yaml` aparecem
automaticamente no prompt, sem tocar aqui. `verificavel_por_texto` é passado
adiante como uma marca `[verificável no texto: sim/não]` para o juiz saber
quando NÃO deve reprovar uma glosa (regras espaciais/não-manuais).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

RULES_PATH = Path(__file__).parent / "rules" / "asl_rules.yaml"


@dataclass(frozen=True)
class Rule:
    id: str
    categoria: str
    titulo: str
    descricao: str
    verificavel_por_texto: bool
    exemplos: list[str] = field(default_factory=list)


def load_rules(path: Path = RULES_PATH) -> list[Rule]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_rules = data.get("rules", [])
    rules: list[Rule] = []
    for entry in raw_rules:
        rules.append(
            Rule(
                id=str(entry["id"]),
                categoria=str(entry.get("categoria", "")),
                titulo=str(entry.get("titulo", "")),
                descricao=" ".join(str(entry.get("descricao", "")).split()),
                verificavel_por_texto=bool(entry.get("verificavel_por_texto", True)),
                exemplos=[str(e) for e in (entry.get("exemplos") or [])],
            )
        )
    return rules


def render_rules(rules: list[Rule]) -> str:
    """Bloco de texto legível para o modelo, uma regra por item."""
    blocks: list[str] = []
    for rule in rules:
        marca = "sim" if rule.verificavel_por_texto else "não"
        lines = [
            f"[{rule.id}] {rule.titulo}  ({rule.categoria}; verificável no texto: {marca})",
            f"  {rule.descricao}",
        ]
        if rule.exemplos:
            lines.append("  Exemplos:")
            lines.extend(f"    - {ex}" for ex in rule.exemplos)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def load_rules_text(path: Path = RULES_PATH) -> str:
    return render_rules(load_rules(path))


def valid_rule_ids(path: Path = RULES_PATH) -> set[str]:
    return {rule.id for rule in load_rules(path)}
