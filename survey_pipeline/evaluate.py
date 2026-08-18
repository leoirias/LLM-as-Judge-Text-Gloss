"""Evaluate (etapa 7). Métricas SEPARADAS (survey §10) — nunca um número só.

Lê o resultado.csv de um experimento e reporta:
  - distribuição de estados (valido/invalido/nao_coberto)
  - cobertura: quanto o validador se ABSTEVE (nao_coberto)
  - eficiência: quanto foi resolvido por código (determinístico) vs LLM
  - parse
  - acurácia PROXY vs ouro: rótulo-ouro = valido se glosa==gloss_review, senão
    invalido (o review "mudou" a glosa). Medido só nas linhas COBERTAS. É proxy —
    o ouro é de superfície e não é gabarito de fidelidade/naturalidade.

Rodar (sem GPU):
    python survey_pipeline/evaluate.py --run survey_pipeline/experiments/<nome>/resultado.csv
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


def _norm(s: str) -> str:
    return " ".join((s or "").split()).rstrip(".").strip().upper()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True, help="resultado.csv de um experimento")
    args = p.parse_args()

    rows = list(csv.DictReader(args.run.open(encoding="utf-8")))
    n = len(rows)
    if not n:
        raise SystemExit("resultado.csv vazio")

    estados = Counter(r["Estado"] for r in rows)
    origem = Counter(r["Origem"] for r in rows)
    cobertas = [r for r in rows if r["Estado"] in ("valido", "invalido")]
    abstencao = estados.get("nao_coberto", 0)

    # acurácia proxy vs ouro (só nas cobertas)
    ok = 0
    for r in cobertas:
        gold = "valido" if _norm(r["Glosa"]) == _norm(r["Glosa Review"]) else "invalido"
        if r["Estado"] == gold:
            ok += 1
    acc = (ok / len(cobertas) * 100) if cobertas else 0.0

    print(f"=== avaliação: {args.run} ===")
    print(f"total de pares: {n}\n")
    print("-- estados --")
    for e, c in estados.most_common():
        print(f"  {e:12s} {c:4d}  ({100*c/n:.1f}%)")
    print(f"\n-- cobertura --")
    print(f"  cobertas (veredito): {len(cobertas)}  ({100*len(cobertas)/n:.1f}%)")
    print(f"  abstenções (nao_coberto): {abstencao}  ({100*abstencao/n:.1f}%)")
    print(f"\n-- eficiência (origem da decisão) --")
    for o, c in origem.most_common():
        print(f"  {o:14s} {c:4d}  ({100*c/n:.1f}%)")
    print(f"\n-- acurácia PROXY vs ouro (só cobertas) --")
    print(f"  concordância com ouro-proxy: {ok}/{len(cobertas)}  ({acc:.1f}%)")
    print("  (proxy: ouro-válido = glosa == gloss_review; superfície, não fidelidade)")


if __name__ == "__main__":
    main()
