"""Etapa 2 (parte 1): classifica as candidatas da etapa 1 em 2 grupos, pelo
campo `verificavel_por_texto` já atribuído na extração:
  - verificavel_por_texto = true  -> voice2sign (texto -> glosa; é o que o
    validador de texto usa/consegue checar)
  - verificavel_por_texto = false -> sign2voice (depende de canal fora do
    texto — expressão facial/não-manual, espaço, movimento; pertence ao
    pipeline inverso, fora do escopo do validador de texto atual)

Mesmo vocabulário que `survey_pipeline/build_rule_package.py` já usa pras
regras da consultoria (asl_rules.yaml) — aplicado aqui às candidatas
extraídas de livro. Consolida TODOS os CSVs de `extraction/output/` (os
vários livros/capítulos) num único par de arquivos por pipeline, porque a
próxima parte da etapa 2 (mesclar duplicatas) precisa enxergar as candidatas
de todos os livros juntas, não capítulo por capítulo.

Não usa modelo/GPU — é só reorganização determinística das colunas que a
extração já preencheu.

`--source X` restringe aos CSVs de extração cujo nome bate com X (ex.:
`--source tania`) e escreve em arquivo SEPARADO (`<source>_voice2sign_
candidatas.csv`), sem tocar no pool principal — útil quando se quer isolar
uma fonte nova pra comparar contra a base já consolidada (etapa 3), em vez
de já misturar tudo de uma vez.

Rodar (sem GPU, direto):
    python asl_pipeline/simplification/classify_pipeline.py
    python asl_pipeline/simplification/classify_pipeline.py --source tania
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
EXTRACTION_OUTPUT = HERE.parent / "extraction" / "output"
OUTPUT_DIR = HERE / "output"

IN_COLS = ["id", "categoria", "titulo", "descricao", "gatilho",
           "verificavel_por_texto", "exemplos", "fonte_livro",
           "fonte_pagina", "fonte_citacao"]
OUT_COLS = ["pipeline", *IN_COLS]


def _chmod(path: Path) -> None:
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass


def _to_bool(v: str) -> bool:
    return str(v).strip().lower() in ("true", "1", "sim", "yes")


def _dedupe_ids(rows: list[dict]) -> list[dict]:
    """Cada CSV de livro numera suas próprias regras a partir de 1 por
    categoria (`extract.py` reinicia o contador por livro) — então, ao
    concatenar 2+ livros aqui, é possível 2 livros diferentes produzirem o
    mesmo ID (ex.: os 2 livros de Libras cada um gerando o próprio
    "LIBRAS.SINTAXE.002"). Renumera só a(s) categoria(s) que realmente
    colidiu(ram); categoria sem colisão mantém o ID original."""
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cat[r["categoria"]].append(r)

    out: list[dict] = []
    for categoria, cat_rows in by_cat.items():
        ids = [r["id"] for r in cat_rows]
        if len(set(ids)) == len(ids):
            out.extend(cat_rows)
            continue
        prefix = cat_rows[0]["id"].split(".")[0]
        for i, r in enumerate(cat_rows, start=1):
            out.append({**r, "id": f"{prefix}.{categoria.upper()}.{i:03d}"})
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=str, default=None,
                    help="processa só o(s) CSV(s) de extração cujo nome contém esse texto; "
                         "escreve em arquivo separado, não mexe no pool principal")
    args = p.parse_args()

    csvs = sorted(EXTRACTION_OUTPUT.glob("*_regras.csv"))
    if args.source:
        csvs = [c for c in csvs if args.source.lower() in c.name.lower()]
        if not csvs:
            raise SystemExit(f"nenhum CSV de extração bate com --source {args.source!r} em {EXTRACTION_OUTPUT}")
    elif not csvs:
        raise SystemExit(f"nenhum CSV encontrado em {EXTRACTION_OUTPUT} — "
                          f"rode a extração (etapa 1) primeiro")

    voice2sign: list[dict] = []
    sign2voice: list[dict] = []
    for path in csvs:
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                pipeline = "voice2sign" if _to_bool(row["verificavel_por_texto"]) else "sign2voice"
                row_out = {"pipeline": pipeline, **row}
                (voice2sign if pipeline == "voice2sign" else sign2voice).append(row_out)

    prefix = f"{args.source}_" if args.source else ""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in [(f"{prefix}voice2sign_candidatas.csv", _dedupe_ids(voice2sign)),
                        (f"{prefix}sign2voice_candidatas.csv", _dedupe_ids(sign2voice))]:
        out = OUTPUT_DIR / name
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=OUT_COLS)
            w.writeheader()
            w.writerows(rows)
        _chmod(out)
        print(f"escrito {out} ({len(rows)} regras)")

    total = len(voice2sign) + len(sign2voice)
    if total:
        print(f"\ntotal: {total} regras | voice2sign: {len(voice2sign)} "
              f"({100 * len(voice2sign) / total:.0f}%) | sign2voice: {len(sign2voice)} "
              f"({100 * len(sign2voice) / total:.0f}%)")


if __name__ == "__main__":
    main()
