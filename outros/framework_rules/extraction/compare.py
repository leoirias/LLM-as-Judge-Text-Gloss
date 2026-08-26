"""CLI de comparação: cada regra extraída do livro x a base da consultoria.

Comparação SEMÂNTICA, regra a regra (uma chamada de LLM por regra extraída),
recebendo toda a base (asl_rules.yaml). Produz um CSV com as colunas da regra
extraída + status (ja_temos/nao_temos/conflito/parcial), a regra da base
correspondente e a justificativa — pronto para a consultoria filtrar.

Rodar (dentro do container, GPU do projeto):

    docker compose exec judge bash -lc '
      PYTHONPATH=src uv run python framework_rules/extraction/compare.py'
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import replace
from pathlib import Path

import yaml
from pydantic import ValidationError

from outros.framework_rules.extraction.llm import generate_batch, get_llm
from outros.framework_rules.extraction.parsing import extract_json
from outros.framework_rules.extraction.prompt import load_prompt_config, render
from outros.framework_rules.extraction.schema import CompareResult

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.yaml"
PROMPT_PATH = HERE / "prompts" / "compare_rule.yaml"

# rules_store vive em framework_rules/ (diretório pai)
sys.path.insert(0, str(HERE.parent))
from outros.framework_rules.rules_store import load_rules, render_rules  # noqa: E402

COMPARE_COLS = ["status", "regra_base_correspondente", "justificativa"]


def _chmod(path: Path) -> None:
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass


def _parse(raw: str) -> CompareResult | None:
    try:
        return CompareResult.model_validate(extract_json(raw))
    except (ValueError, ValidationError):
        return None


def _generate_thinking_off(llm, prompts, chunk):
    """Fallback: gera com thinking off + teto baixo, reusando o mesmo modelo."""
    original = llm.config
    llm.config = replace(
        original,
        chat_template=replace(original.chat_template, enable_thinking=False),
        generation=replace(original.generation, max_new_tokens=512),
    )
    try:
        return generate_batch(llm, prompts, chunk=chunk)
    finally:
        llm.config = original


def main() -> None:
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    io = cfg["io"]

    p = argparse.ArgumentParser()
    p.add_argument("--rules", type=Path, default=None,
                   help="CSV de regras extraídas (saída do extract.py)")
    p.add_argument("--base", type=Path, default=Path(cfg["base_rules"]),
                   help="base de regras da consultoria (asl_rules.yaml)")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--full", action="store_true", help="compara o CSV do livro inteiro")
    p.add_argument("--pairs", action="store_true", help="compara o CSV induzido dos pares-ouro")
    p.add_argument("--mp", action="store_true",
                   help="compara as regras da convenção do main_pipeline")
    args = p.parse_args()

    if args.full:
        args.rules = args.rules or Path(io["full_rules_out"])
        args.out = args.out or Path(io["full_compare_out"])
    elif args.pairs:
        args.rules = args.rules or Path(io["pairs_rules_out"])
        args.out = args.out or Path(io["pairs_compare_out"])
    elif args.mp:
        args.rules = args.rules or Path(io["mp_rules"])
        args.out = args.out or Path(io["mp_compare_out"])
    else:
        args.rules = args.rules or Path(io["rules_out"])
        args.out = args.out or Path(io["compare_out"])

    extracted = list(csv.DictReader(args.rules.open(encoding="utf-8")))
    print(f"{len(extracted)} regras extraídas de {args.rules}")

    base_text = render_rules(load_rules(args.base))
    prompt_config = load_prompt_config(PROMPT_PATH)
    prompts = [
        render(prompt_config, {
            "base_rules": base_text,
            "regra_id": r.get("id", ""),
            "regra_categoria": r.get("categoria", ""),
            "regra_titulo": r.get("titulo", ""),
            "regra_descricao": r.get("descricao", ""),
            "regra_gatilho": r.get("gatilho", ""),
            "regra_verificavel": r.get("verificavel_por_texto", ""),
        })
        for r in extracted
    ]

    llm = get_llm()
    chunk = int(cfg.get("batch_size", 4))
    raw_responses = generate_batch(llm, prompts, chunk=chunk)
    results = [_parse(r) for r in raw_responses]

    # rede de segurança: reprocessa quem não parseou com thinking off
    fb = [i for i, res in enumerate(results) if res is None]
    if fb:
        print(f"reprocessando {len(fb)} comparação(ões) sem parse com thinking OFF...")
        retry = _generate_thinking_off(llm, [prompts[i] for i in fb], chunk)
        for i, raw in zip(fb, retry):
            results[i] = _parse(raw)

    in_cols = list(extracted[0].keys()) if extracted else []
    out_cols = in_cols + COMPARE_COLS
    counts: dict[str, int] = {}
    parse_failed = 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=out_cols)
        w.writeheader()
        for r, res in zip(extracted, results):
            row = dict(r)
            if res is not None:
                row["status"] = res.status
                row["regra_base_correspondente"] = res.regra_base_correspondente
                row["justificativa"] = res.justificativa
                counts[res.status] = counts.get(res.status, 0) + 1
            else:
                row["status"] = "parse_falhou"
                row["regra_base_correspondente"] = ""
                row["justificativa"] = ""
                parse_failed += 1
            w.writerow(row)
    _chmod(args.out)

    print(f"escrito {args.out}")
    for status, n in sorted(counts.items()):
        print(f"  {status}: {n}")
    if parse_failed:
        print(f"  parse_falhou: {parse_failed}")


if __name__ == "__main__":
    main()
