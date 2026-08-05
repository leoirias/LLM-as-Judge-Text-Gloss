"""CLI de extração: livro -> CSV de regras NORMALIZADAS.

Uma chamada de LLM (qwen3-32B, thinking on) lê o texto e extrai as regras
gramaticais relevantes para entender/representar a estrutura da ASL, no schema
da base + gatilho + procedência. Grava um CSV pronto para a consultoria conferir.

Modos:
  (default)   um capítulo/faixa de páginas (--start-page/--end-page) -> 1 chamada
  --full      livro inteiro, fatiado em janelas de `window_pages` páginas
              (1 chamada por janela); junta tudo num CSV só
  --from-raw  reconstrói o CSV a partir do *.raw.txt já salvo, sem chamar o modelo

Rodar (dentro do container, GPU do projeto):

    docker compose exec judge bash -lc '
      PYTHONPATH=src uv run python framework_rules/extraction/extract.py'          # cap.2
    docker compose exec judge bash -lc '
      PYTHONPATH=src uv run python framework_rules/extraction/extract.py --full'    # livro inteiro
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import yaml
from pydantic import ValidationError
from tqdm import tqdm

from llm import get_llm
from parsing import extract_json
from pdf_text import extract_pages
from prompt import load_prompt_config, render
from schema import ExtractedRule, ExtractedRuleSet

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.yaml"
PROMPT_PATH = HERE / "prompts" / "extract_rules.yaml"

CSV_COLS = ["id", "categoria", "titulo", "descricao", "gatilho",
            "verificavel_por_texto", "exemplos", "fonte_pagina", "fonte_citacao"]


def _chmod(path: Path) -> None:
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass


def _parse_rules(raw: str) -> list[ExtractedRule]:
    return ExtractedRuleSet.model_validate(extract_json(raw)).rules


def _write_csv(rules: list[ExtractedRule], out: Path) -> None:
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLS)
        w.writeheader()
        for r in rules:
            w.writerow({
                "id": r.id,
                "categoria": r.categoria,
                "titulo": r.titulo,
                "descricao": r.descricao,
                "gatilho": r.gatilho,
                "verificavel_por_texto": r.verificavel_por_texto,
                "exemplos": " ; ".join(r.exemplos),
                "fonte_pagina": r.fonte_pagina,
                "fonte_citacao": r.fonte_citacao,
            })
    _chmod(out)


def _run_full(cfg: dict, pdf: Path, out: Path) -> None:
    """Livro inteiro: janelas de páginas, 1 chamada por janela, tudo num CSV."""
    book = cfg["book"]
    start = int(book["content_start_page"])
    end = int(book["content_end_page"])
    win = int(book["window_pages"])
    windows = [(s, min(s + win - 1, end)) for s in range(start, end + 1, win)]
    print(f"livro inteiro: {len(windows)} janelas de {win} págs (p.{start}-{end})")

    llm = get_llm()
    prompt_config = load_prompt_config(PROMPT_PATH)
    all_rules: list[ExtractedRule] = []
    raw_chunks: list[str] = []

    for s, e in tqdm(windows, desc="Extraindo (janelas)", unit="janela"):
        text = extract_pages(pdf, s, e)
        raw = llm.generate(render(prompt_config, {"chapter_text": text}))
        raw_chunks.append(f"### p.{s}-{e}\n{raw}")
        try:
            all_rules.extend(_parse_rules(raw))
        except (ValueError, ValidationError) as exc:
            print(f"  janela {s}-{e}: parse falhou, pulada ({exc})")

    # IDs globais sequenciais (o modelo numera por janela e colidiria)
    for n, r in enumerate(all_rules, start=1):
        r.id = f"ASLFD.{n:03d}"

    out.parent.mkdir(parents=True, exist_ok=True)
    raw_path = out.with_suffix(".raw.txt")
    raw_path.write_text("\n\n".join(raw_chunks), encoding="utf-8")
    _chmod(raw_path)
    _write_csv(all_rules, out)
    print(f"escrito {out}  ({len(all_rules)} regras de {len(windows)} janelas)")


def main() -> None:
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    book = cfg["book"]
    io = cfg["io"]

    p = argparse.ArgumentParser()
    p.add_argument("--pdf", type=Path, default=Path(book["path"]))
    p.add_argument("--start-page", type=int, default=int(book["start_page"]))
    p.add_argument("--end-page", type=int, default=int(book["end_page"]))
    p.add_argument("--out", type=Path, default=None,
                   help="CSV de saída (default: rules_out; full_rules_out se --full)")
    p.add_argument("--full", action="store_true", help="extrai o livro inteiro (por janelas)")
    p.add_argument("--from-raw", action="store_true",
                   help="reconstrói o CSV a partir do *.raw.txt já salvo, sem chamar o modelo")
    args = p.parse_args()

    if args.full:
        out = args.out or Path(io["full_rules_out"])
        _run_full(cfg, args.pdf, out)
        return

    out = args.out or Path(io["rules_out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    raw_path = out.with_suffix(".raw.txt")

    if args.from_raw:
        print(f"reconstruindo CSV a partir de {raw_path} (sem GPU)")
        raw = raw_path.read_text(encoding="utf-8")
    else:
        print(f"lendo {args.pdf} páginas {args.start_page}-{args.end_page} "
              f"({book.get('chapter_label','')})")
        text = extract_pages(args.pdf, args.start_page, args.end_page)
        prompt_config = load_prompt_config(PROMPT_PATH)
        print("extraindo regras com o LLM (thinking on)...")
        raw = get_llm().generate(render(prompt_config, {"chapter_text": text}))
        raw_path.write_text(raw, encoding="utf-8")

    try:
        rules = _parse_rules(raw)
    except (ValueError, ValidationError) as exc:
        raise SystemExit(
            f"falha ao parsear/validar as regras extraídas: {exc}\n"
            f"resposta crua salva em {raw_path}"
        )
    _write_csv(rules, out)
    _chmod(raw_path)
    print(f"escrito {out}  ({len(rules)} regras)")


if __name__ == "__main__":
    main()
