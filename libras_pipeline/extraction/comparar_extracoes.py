"""Compara duas extrações da MESMA fonte, feitas com fatiamentos diferentes.

Uso:
    python libras_pipeline/extraction/comparar_extracoes.py \
        --a output --b output_topicos --slug libras_gramatica_cap5

Eixos medidos (todos verificáveis, nenhum depende de julgamento):
  1. volume de regras, total e por categoria
  2. trechos perdidos por falha de parse
  3. cobertura do capítulo — páginas distintas citadas em fonte_pagina
  4. distribuição de verificavel_por_texto (o que sobra para o juiz)
  5. fenômenos-alvo: regras que sabemos que faltavam (preposição, verbo modal
     como verbo principal, referente presente)
  6. qualidade da citação: fonte_citacao presente e realmente verbatim no PDF
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]

ALVOS = {
    "preposição":            ["preposi"],
    "verbo modal principal": ["modal"],
    "referente presente":    ["referente present", "referente estiver present", "referente presente"],
    "item-QU / interrogativa": ["qu-", "item qu", "interrogativ"],
    "negação":               ["negaç", "negac"],
}


def carrega(d: Path, slug: str) -> list[dict]:
    p = d / f"{slug}_regras.csv"
    if not p.exists():
        raise SystemExit(f"não existe: {p}")
    with p.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def trechos_no_raw(d: Path, slug: str) -> int:
    p = d / f"{slug}_regras.raw.txt"
    if not p.exists():
        return 0
    return len(re.findall(r"^### p\.\d+-\d+$", p.read_text(encoding="utf-8"), re.M))


def bate(r: dict, termos: list[str]) -> bool:
    blob = " ".join(r.get(c, "") for c in ("titulo", "descricao", "gatilho")).lower()
    return any(t in blob for t in termos)


def verdadeiro(v: str) -> bool:
    return str(v).strip().lower() in ("true", "1", "sim", "yes")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="output", help="extração A (baseline)")
    ap.add_argument("--b", default="output_topicos", help="extração B (nova)")
    ap.add_argument("--slug", default="libras_gramatica_cap5")
    ap.add_argument("--rotulo-a", default="janela 15p")
    ap.add_argument("--rotulo-b", default="por tópico")
    args = ap.parse_args()

    da, db = HERE / args.a, HERE / args.b
    A, B = carrega(da, args.slug), carrega(db, args.slug)
    ra, rb = args.rotulo_a, args.rotulo_b
    W = max(len(ra), len(rb), 12)

    print("=" * 84)
    print(f"COMPARAÇÃO — {args.slug}")
    print(f"   A = {ra}  ({da})")
    print(f"   B = {rb}  ({db})")
    print("=" * 84)

    print("\n1. VOLUME")
    ta, tb = trechos_no_raw(da, args.slug), trechos_no_raw(db, args.slug)
    print(f"   {ra:<{W}}  {len(A):>4} regras em {ta:>3} trechos  ({len(A)/max(ta,1):.1f} por trecho)")
    print(f"   {rb:<{W}}  {len(B):>4} regras em {tb:>3} trechos  ({len(B)/max(tb,1):.1f} por trecho)")
    print(f"   delta: {len(B)-len(A):+d} regras")

    print("\n2. COBERTURA DO CAPÍTULO (páginas distintas citadas)")
    for rot, X in ((ra, A), (rb, B)):
        pgs = {r["fonte_pagina"] for r in X if r.get("fonte_pagina", "").strip()}
        print(f"   {rot:<{W}}  {len(pgs):>3} páginas distintas")

    print("\n3. CANAL (verificavel_por_texto)")
    for rot, X in ((ra, A), (rb, B)):
        v = sum(1 for r in X if verdadeiro(r.get("verificavel_por_texto", "")))
        pct = 100 * v / len(X) if X else 0
        print(f"   {rot:<{W}}  voice2sign {v:>4} ({pct:.0f}%)  |  sign2voice {len(X)-v:>4}")

    print("\n4. CATEGORIAS")
    ca, cb = Counter(r["categoria"] for r in A), Counter(r["categoria"] for r in B)
    print(f"   {'categoria':<22} {ra:>{W}} {rb:>{W}}   delta")
    for cat in sorted(set(ca) | set(cb), key=lambda c: -(ca[c] + cb[c])):
        print(f"   {cat:<22} {ca[cat]:>{W}} {cb[cat]:>{W}}   {cb[cat]-ca[cat]:+d}")

    print("\n5. FENÔMENOS-ALVO (os que sabíamos faltar)")
    print(f"   {'fenômeno':<26} {ra:>{W}} {rb:>{W}}")
    for nome, termos in ALVOS.items():
        na = sum(1 for r in A if bate(r, termos))
        nb = sum(1 for r in B if bate(r, termos))
        marca = "  <-- novo" if nb and not na else ""
        print(f"   {nome:<26} {na:>{W}} {nb:>{W}}{marca}")

    print("\n6. QUALIDADE DA CITAÇÃO")
    for rot, X in ((ra, A), (rb, B)):
        com = [r for r in X if r.get("fonte_citacao", "").strip()]
        curtas = sum(1 for r in com if len(r["fonte_citacao"]) < 25)
        print(f"   {rot:<{W}}  com citação {len(com):>4}/{len(X):<4}  "
              f"({100*len(com)//max(len(X),1)}%)  |  citação <25 chars: {curtas}")

    print("\n7. REGRAS SÓ EM B (títulos novos, amostra)")
    tit_a = {r["titulo"].strip().lower() for r in A}
    novas = [r for r in B if r["titulo"].strip().lower() not in tit_a]
    print(f"   {len(novas)} regras com título inédito em B")
    for r in novas[:15]:
        print(f"     [{r['id']}] {r['titulo'][:66]}")


if __name__ == "__main__":
    main()
