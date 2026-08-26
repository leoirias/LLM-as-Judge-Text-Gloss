"""Compara duas rodadas do passo 5 (fusão) sobre as MESMAS candidatas.

    python comparar_fusao.py --a output_v2 --b output_v2_automat --source cap5

Mede o que importa numa fusão: quanto reduziu, quantas regras de fato fundiram
(mais de um id_origem), e se alguma candidata se perdeu no caminho.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

HERE = Path(__file__).parent


def ler(d: str, nome: str) -> list[dict] | None:
    p = HERE / d / nome
    if not p.exists():
        return None
    with p.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def origens(rows: list[dict]) -> list[int]:
    return [len([x for x in r["ids_origem"].split(";") if x.strip()]) for r in rows]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="output_v2", help="rodada de referência")
    ap.add_argument("--b", default="output_v2_automat", help="rodada nova")
    ap.add_argument("--source", action="append", default=None)
    ap.add_argument("--group", default="voice2sign")
    args = ap.parse_args()
    fontes = args.source or ["cap5", "gramatica2"]

    print(f"{'fonte':<14} {'cand':>5} | {'A finais':>9} {'A fund':>7} | "
          f"{'B finais':>9} {'B fund':>7} | {'ganho':>7}")
    print("=" * 74)
    for src in fontes:
        cand = ler(args.a, f"{src}_{args.group}_candidatas.csv")
        A = ler(args.a, f"{src}_{args.group}_final.csv")
        B = ler(args.b, f"{src}_{args.group}_final.csv")
        if cand is None or A is None:
            print(f"{src:<14} falta a rodada A"); continue
        if B is None:
            print(f"{src:<14} {len(cand):>5} | {len(A):>9} {sum(1 for n in origens(A) if n>1):>7} | "
                  f"{'—':>9} {'—':>7} |  (B ainda não rodou)")
            continue
        fa, fb = sum(1 for n in origens(A) if n > 1), sum(1 for n in origens(B) if n > 1)
        print(f"{src:<14} {len(cand):>5} | {len(A):>9} {fa:>7} | {len(B):>9} {fb:>7} | "
              f"{len(A)-len(B):>+7}")

        cov_a = {i for r in A for i in r["ids_origem"].split(";") if i.strip()}
        cov_b = {i for r in B for i in r["ids_origem"].split(";") if i.strip()}
        todas = {r["id"] for r in cand}
        for rot, cov in (("A", cov_a), ("B", cov_b)):
            perdidas = todas - {c.strip() for c in cov}
            if perdidas:
                print(f"   [{rot}] {len(perdidas)} candidata(s) PERDIDAS: {sorted(perdidas)[:5]}")
        novas = [r for r, n in zip(B, origens(B)) if n > 1]
        if novas:
            print(f"   fusões em B (amostra):")
            for r in novas[:4]:
                print(f"     {r['titulo'][:52]:<52} <- {r['ids_origem'][:44]}")


if __name__ == "__main__":
    main()
