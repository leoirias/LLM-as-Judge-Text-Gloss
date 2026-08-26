"""Etapa 2 parte 3 (sob demanda): compara as candidatas de UMA fonte nova
(ex.: as regras extraídas do documento da Tânia, via `classify_pipeline.py
--source tania`) contra a base já consolidada (voice2sign_final.csv), pra
decidir se cada fenômeno já está coberto e, se sim, se é consistente ou
conflitante com o que já temos.

1 chamada de LLM por candidata (recebe a candidata + a base inteira como
contexto). Não funde nem altera a base — só classifica. A decisão de
incorporar (`nao_temos`), resolver conflito (`conflito`) ou revisar
(`parcial`) fica pra revisão humana depois, olhando o CSV de saída.

Rodar (dentro do container, GPU do projeto):
    docker compose exec -e CUDA_VISIBLE_DEVICES=<N> judge bash -lc \
      'PYTHONPATH=src uv run python libras_pipeline/simplification/compare_rules.py --source tania'
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

from pydantic import ValidationError
from tqdm import tqdm

from llm import get_llm
from parsing import extract_json
from prompt import load_prompt_config, render
from schema import CompareResult

HERE = Path(__file__).parent
PROMPT_PATH = HERE / "prompts" / "compare_rule.yaml"
OUTPUT_DIR = HERE / "output"
BASE_PATH = OUTPUT_DIR / "voice2sign_final.csv"

OUT_COLS = ["id", "categoria", "titulo", "descricao", "gatilho", "exemplos",
            "fonte_livro", "fonte_pagina", "fonte_citacao",
            "status", "regra_base_correspondente", "justificativa"]


def _chmod(path: Path) -> None:
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass


def _load_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _render_base(rows: list[dict]) -> str:
    blocks = []
    for r in rows:
        blocks.append(f"[{r['id']}] {r['titulo']} ({r['categoria']})\n"
                       f"  {r['descricao']}\n  gatilho: {r['gatilho']}")
    return "\n\n".join(blocks)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=str, required=True,
                    help="prefixo do arquivo de candidatas a comparar "
                         "(ex.: tania -> tania_voice2sign_candidatas.csv)")
    args = p.parse_args()

    cand_path = OUTPUT_DIR / f"{args.source}_voice2sign_candidatas.csv"
    if not cand_path.exists():
        raise SystemExit(f"{cand_path} não existe — rode "
                          f"'classify_pipeline.py --source {args.source}' primeiro")
    if not BASE_PATH.exists():
        raise SystemExit(f"{BASE_PATH} não existe — rode merge_rules.py primeiro (base já consolidada)")

    candidatas = _load_csv(cand_path)
    base_rows = _load_csv(BASE_PATH)
    base_text = _render_base(base_rows)
    print(f"{len(candidatas)} candidatas de '{args.source}' vs {len(base_rows)} regras já na base")

    prompt_config = load_prompt_config(PROMPT_PATH)
    llm = get_llm()

    out_rows = []
    counts: dict[str, int] = {}
    raw_log = OUTPUT_DIR / f"{args.source}_comparacao.raw.txt"
    raw_log.write_text("", encoding="utf-8")

    for r in tqdm(candidatas, desc="Comparando", unit="regra"):
        prompt = render(prompt_config, {
            "base": base_text,
            "candidata_id": r["id"], "candidata_titulo": r["titulo"],
            "candidata_descricao": r["descricao"], "candidata_gatilho": r["gatilho"],
            "candidata_exemplos": r["exemplos"],
        })
        raw = llm.generate(prompt)
        with raw_log.open("a", encoding="utf-8") as fh:
            fh.write(f"### {r['id']}\n{raw}\n\n")
        try:
            data = extract_json(raw)
            res = CompareResult.model_validate(data)
        except (ValueError, ValidationError) as exc:
            print(f"  {r['id']}: parse falhou ({exc}) — marcado p/ revisão manual")
            res = CompareResult(status="nao_temos", justificativa=f"[REVISAR: parse falhou] {exc}")

        counts[res.status] = counts.get(res.status, 0) + 1
        out_rows.append({
            "id": r["id"], "categoria": r["categoria"], "titulo": r["titulo"],
            "descricao": r["descricao"], "gatilho": r["gatilho"], "exemplos": r["exemplos"],
            "fonte_livro": r["fonte_livro"], "fonte_pagina": r["fonte_pagina"],
            "fonte_citacao": r["fonte_citacao"],
            "status": res.status, "regra_base_correspondente": res.regra_base_correspondente,
            "justificativa": res.justificativa,
        })

    out_path = OUTPUT_DIR / f"{args.source}_comparacao.csv"
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLS)
        w.writeheader()
        w.writerows(out_rows)
    _chmod(out_path)

    print(f"\nescrito {out_path}")
    print(f"status: {counts}")


if __name__ == "__main__":
    main()
