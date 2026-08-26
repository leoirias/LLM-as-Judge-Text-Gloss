"""Orquestrador do validador (Pipeline 2). Ordem do survey:
determinístico -> resíduo LLM -> interpret (3 estados) -> escreve.

Rodar (dentro do container; escolha a GPU no comando):
    docker compose exec -e CUDA_VISIBLE_DEVICES=4 judge bash -lc \
      'PYTHONPATH=src uv run python survey_pipeline/run.py --limit 1 --exp-name smoke'
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import yaml

from outros.survey_pipeline.coverage import consolidate
from judge import build_prompt, build_rules_text, count_rules, load_package
from outros.survey_pipeline.llm import generate_batch, get_llm
from outros.survey_pipeline.parsing import JudgeParseError, parse_verdict
from outros.survey_pipeline.prompt import load_prompt

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.yaml"

CSV_COLS = ["Texto", "Glosa", "Estado", "Fidelidade", "Naturalidade",
            "Regras", "Problema", "Sugestao", "Glosa Review", "Origem"]


def _chmod(p: Path) -> None:
    try:
        os.chmod(p, 0o777 if p.is_dir() else 0o666)
    except OSError:
        pass


def read_pairs(path: Path, io: dict) -> list[dict]:
    rows = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            text = (r.get(io.get("text_col", "Input")) or "").strip()
            if not text:
                continue
            rows.append({
                "text": text,
                "gloss": (r.get(io.get("gloss_col", "Output")) or "").strip(),
                "review": (r.get(io.get("review_col", "Output review")) or "").strip(),
            })
    return rows


def _generate_thinking_off(llm, prompts, chunk):
    original = llm.config
    llm.config = replace(
        original,
        chat_template=replace(original.chat_template, enable_thinking=False),
        generation=replace(original.generation, max_new_tokens=512),
    )
    try:
        return generate_batch(llm, prompts, chunk=chunk, desc="Fallback thinking-off")
    finally:
        llm.config = original


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, default=CONFIG_PATH,
                   help="config da língua (config.yaml = ASL; config_libras.yaml = Libras)")
    p.add_argument("--input", type=Path, default=None)
    p.add_argument("--exp-name", type=str, default="")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    io = cfg["io"]
    input_path = args.input or Path(io["input"])

    package = load_package(io["rule_package"])
    rules_text = build_rules_text(package)
    n_rules = count_rules(package)
    prompt_dict = load_prompt(io["prompt"])

    # camada determinística: só ativa se o pacote tiver regra dura/aviso
    # (ASL v1.0 e gramática Libras v1: ainda não têm -> LLM decide, sem parser)
    det_enabled = any(r.get("enforcement") in ("dura", "aviso") for r in package.get("rules", []))
    achados_default = "nenhum"

    pairs = read_pairs(input_path, io)
    if args.limit is not None:
        pairs = pairs[: args.limit]
    print(f"[{io.get('lingua','?')}] {len(pairs)} pares | {n_rules} regras | determinístico ativo: {det_enabled}")

    prompts = [build_prompt(prompt_dict, pr["text"], pr["gloss"], rules_text, achados_default)
               for pr in pairs]

    llm = get_llm()
    chunk = int(cfg.get("batch_size", 8))
    raw = generate_batch(llm, prompts, chunk=chunk, desc="Validando glosas")

    raw_final = list(raw)          # resposta usada em cada linha (p/ salvar)
    err_msg: list[str | None] = [None] * len(raw)
    verdicts, fail_idx = [], []
    for i, r in enumerate(raw):
        try:
            verdicts.append(parse_verdict(r))
        except JudgeParseError as exc:
            verdicts.append(None)
            err_msg[i] = str(exc)
            fail_idx.append(i)

    if fail_idx:
        print(f"fallback thinking-off em {len(fail_idx)} resposta(s) sem parse...")
        retry = _generate_thinking_off(llm, [prompts[i] for i in fail_idx], chunk)
        for i, rr in zip(fail_idx, retry):
            raw_final[i] = rr
            try:
                verdicts[i] = parse_verdict(rr)
                err_msg[i] = None
            except JudgeParseError as exc:
                verdicts[i] = None
                err_msg[i] = str(exc)

    # pasta de experimento
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    name = args.exp_name.strip() or f"{stamp}_{io.get('lingua','x')}_v1"
    exp = Path(io["experiments_dir"]) / name
    exp.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    parse_failed = 0
    with (exp / "resultado.csv").open("w", newline="", encoding="utf-8") as fh, \
         (exp / "raw.jsonl").open("w", encoding="utf-8") as raw_fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLS)
        w.writeheader()
        for i, (pr, v) in enumerate(zip(pairs, verdicts)):
            d = consolidate([], v)  # v1.0: sem findings determinísticos
            if v is None:
                parse_failed += 1
            counts[d.estado] = counts.get(d.estado, 0) + 1
            w.writerow({
                "Texto": pr["text"], "Glosa": pr["gloss"], "Estado": d.estado,
                "Fidelidade": d.representa_sentido, "Naturalidade": d.natural_estrutura,
                "Regras": "; ".join(d.regras), "Problema": d.problema,
                "Sugestao": d.sugestao, "Glosa Review": pr["review"], "Origem": d.origem,
            })
            raw_fh.write(json.dumps({
                "text": pr["text"], "gloss": pr["gloss"],
                "raw": raw_final[i], "parse_error": err_msg[i],
            }, ensure_ascii=False) + "\n")

    meta = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "lingua": io.get("lingua", package.get("meta", {}).get("lingua", "?")),
        "rule_package_versao": package.get("meta", {}).get("versao") or package.get("meta", {}).get("versao_transcricao"),
        "model": cfg["model"]["name"],
        "generation": cfg.get("generation", {}),
        "n_pares": len(pairs),
        "n_regras": n_rules,
        "deterministico_ativo": det_enabled,
        "estados": counts,
        "parse_failed": parse_failed,
    }
    (exp / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    _chmod(exp)
    for f in exp.iterdir():
        _chmod(f)

    print(f"escrito {exp/'resultado.csv'}")
    print(f"  estados={counts}  parse_failed={parse_failed}")


if __name__ == "__main__":
    main()
