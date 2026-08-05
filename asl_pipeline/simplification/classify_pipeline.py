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

Rodar (sem GPU, direto):
    python asl_pipeline/simplification/classify_pipeline.py
"""

from __future__ import annotations

import csv
import os
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


def main() -> None:
    csvs = sorted(EXTRACTION_OUTPUT.glob("*_regras.csv"))
    if not csvs:
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

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in [("voice2sign_candidatas.csv", voice2sign),
                        ("sign2voice_candidatas.csv", sign2voice)]:
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
