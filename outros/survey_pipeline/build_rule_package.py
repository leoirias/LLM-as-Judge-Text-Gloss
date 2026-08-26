"""Gera rules/rule_package.yaml — o pacote de regras VERSIONADO do validador
(etapas Acquire+Formalize do survey; Tab. 5 "Regras").

v1.0: baseado SOMENTE nas regras que a consultoria apresentou (asl_rules.yaml).
As regras extraídas de livros são candidatas (outro pipeline) e só entram depois
de aprovadas pela consultoria — numa versão futura.

Cada regra ganha:
  - pipeline:    voice2sign (texto→glosa, verificável no texto) | sign2voice (vídeo→glosa)
  - enforcement: referencia (o LLM consulta) | fora_escopo_texto (abstém — canal de vídeo)
                 (asl_rules não tem regra de superfície -> não há dura/aviso aqui)
  - dimensao, exemplos, contraexemplos, conflita_com

Rodar (sem GPU):  python survey_pipeline/build_rule_package.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BASE_YAML = ROOT / "framework_rules/rules/asl_rules.yaml"
OUT = Path(__file__).parent / "rules" / "rule_package.yaml"

# conflitos/decisões já resolvidos no SPECIFY (registrados p/ auditoria)
CONFLITA = {
    "PRON.2.1": "convenção derruba o pronome vs. PRON.2.1 lista PRO.x — "
                "RESOLVIDO (SPECIFY): pronome é opcional, presença não é erro (pode ser flag).",
}


def load_consultancy() -> list[dict]:
    data = yaml.safe_load(BASE_YAML.read_text(encoding="utf-8")) or {}
    out = []
    for r in data.get("rules", []):
        verif = bool(r.get("verificavel_por_texto", True))
        out.append({
            "id": r["id"],
            "origem": "consultoria (asl_rules)",
            "categoria": r.get("categoria", ""),
            "pipeline": "voice2sign" if verif else "sign2voice",
            "enforcement": "referencia" if verif else "fora_escopo_texto",
            "dimensao": "estrutura",
            "verificavel_por_texto": verif,
            "descricao": " ".join(str(r.get("descricao", "")).split()),
            "exemplos": [str(e) for e in (r.get("exemplos") or [])],
            "contraexemplos": [],
            "conflita_com": CONFLITA.get(r["id"], ""),
            "fonte": "asl_rules.yaml",
        })
    return out


def main() -> None:
    rules = load_consultancy()
    package = {
        "meta": {
            "versao": "1.0.0",
            "gerado_em": date.today().isoformat(),
            "lingua": "asl",
            "construto": "ver survey_pipeline/SPECIFY.md — glosa fiel ao sentido/intenção, "
                         "fluida e natural, respeitando a estrutura da língua",
            "fonte": "asl_rules.yaml (regras apresentadas pela consultoria)",
            "n_regras": len(rules),
            "nota": "regras extraídas de livros são candidatas (pipeline de extração) e entram só após aprovação da consultoria",
        },
        "enforcement_legenda": {
            "referencia": "norma descritiva; o LLM consulta como contexto (não é check duro)",
            "fora_escopo_texto": "depende de canal fora do texto (espaço/expressão/movimento) -> Sign2Voice; o validador de texto se abstém",
            "dura": "(reservado) check por código, erro certo — não há em v1.0 (asl_rules não tem regra de superfície)",
            "aviso": "(reservado) check por código com exceção — não há em v1.0",
        },
        "pipeline_legenda": {
            "voice2sign": "texto -> glosa; regra usada por ESTE validador",
            "sign2voice": "vídeo -> glosa; regra do pipeline inverso; fora deste validador",
        },
        "rules": rules,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(yaml.safe_dump(package, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8")

    from collections import Counter
    pipe = Counter(r["pipeline"] for r in rules)
    print(f"escrito {OUT}  ({len(rules)} regras)")
    print("por pipeline:", dict(pipe), "| voice2sign =", pipe["voice2sign"], "(as que o validador usa)")


if __name__ == "__main__":
    main()
