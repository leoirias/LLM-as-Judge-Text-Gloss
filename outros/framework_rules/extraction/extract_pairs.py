"""CLI de indução: pares-ouro (Text, Gloss) -> CSV de regras que a convenção segue.

Uma chamada de LLM (qwen3-32B, thinking on) lê TODOS os pares e induz as regras
gramaticais recorrentes. Mesmo schema/CSV da extração de livro, então a saída
entra direto no compare.py para comparar com a base da consultoria.

Rodar (dentro do container, GPU do projeto):

    docker compose exec judge bash -lc '
      PYTHONPATH=src uv run python framework_rules/extraction/extract_pairs.py'
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from outros.framework_rules.extraction.extract import CSV_COLS, _parse_rules, _write_csv  # reusa helpers
from outros.framework_rules.extraction.llm import get_llm
from outros.framework_rules.extraction.prompt import load_prompt_config, render

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.yaml"
PROMPT_PATH = HERE / "prompts" / "extract_from_pairs.yaml"


def _read_pairs(path: Path) -> str:
    """Lê pares (Text/Gloss ou input/output) e monta o bloco 'frase -> glosa'."""
    lines: list[str] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = {c.strip().lower(): c for c in (reader.fieldnames or [])}
        tcol = cols.get("text") or cols.get("input")
        gcol = cols.get("gloss") or cols.get("output")
        if not tcol or not gcol:
            raise SystemExit(f"{path.name}: preciso de colunas text/gloss (tem {list(cols)})")
        for r in reader:
            t = (r.get(tcol) or "").strip()
            g = (r.get(gcol) or "").strip()
            if t and g:
                lines.append(f"{t} -> {g}")
    return "\n".join(lines)


def main() -> None:
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    io = cfg["io"]

    p = argparse.ArgumentParser()
    p.add_argument("--pairs", type=Path, default=Path(cfg["gold_pairs"]))
    p.add_argument("--out", type=Path, default=Path(io["pairs_rules_out"]))
    p.add_argument("--from-raw", action="store_true",
                   help="reconstrói o CSV a partir do *.raw.txt salvo, sem GPU")
    args = p.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    raw_path = args.out.with_suffix(".raw.txt")

    if args.from_raw:
        print(f"reconstruindo CSV a partir de {raw_path} (sem GPU)")
        raw = raw_path.read_text(encoding="utf-8")
    else:
        pairs_text = _read_pairs(args.pairs)
        n = pairs_text.count("\n") + 1 if pairs_text else 0
        print(f"induzindo regras de {n} pares de {args.pairs} (thinking on)...")
        prompt_config = load_prompt_config(PROMPT_PATH)
        raw = get_llm().generate(render(prompt_config, {"pairs": pairs_text}))
        raw_path.write_text(raw, encoding="utf-8")
        try:
            os.chmod(raw_path, 0o666)
        except OSError:
            pass

    try:
        rules = _parse_rules(raw)
    except (ValueError, ValidationError) as exc:
        raise SystemExit(f"falha ao parsear/validar: {exc}\nresposta crua em {raw_path}")

    _write_csv(rules, args.out)
    print(f"escrito {args.out}  ({len(rules)} regras induzidas)")


if __name__ == "__main__":
    main()
