"""CLI do juiz guiado por regras.

Lê data/pares_review.csv (Input = texto, Output = glosa proposta, Output review
= validação manual de referência), injeta a base de regras (rules/asl_rules.yaml)
no prompt, roda o qwen3-32B (thinking on, temp 0.5) e escreve o resultado numa
PASTA DE EXPERIMENTO própria para cada rodada:

  framework_rules/experiments/<data>_<nome>/
    config.yaml         snapshot exato dos parâmetros usados
    teste_inicial.csv   Texto | Glosa | Correto? | Regras | Sugestao | Glosa Review
    meta.json           timestamp, modelo, nº de linhas, contagem Sim/Não, versão das regras
    raw.jsonl           respostas cruas do juiz (debug / reprocesso sem re-rodar o modelo)

Rodar (dentro do container, GPU do projeto):

    docker compose exec judge bash -lc '
      PYTHONPATH=src python framework_rules/run.py'
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import yaml

from outros.framework_rules.llm import generate_batch, get_llm
from outros.framework_rules.parsing import JudgeParseError, parse_judge_response
from outros.framework_rules.prompt import PROMPT_PATH, build_judge_prompt, load_prompt_config
from outros.framework_rules.rules_store import RULES_PATH, load_rules_text, valid_rule_ids

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.yaml"


def read_pairs(path: Path, text_col: str, gloss_col: str, review_col: str) -> list[dict]:
    rows: list[dict] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames or []
        for req in (text_col, gloss_col):
            if req not in cols:
                raise SystemExit(f"{path.name}: coluna {req!r} ausente (tem {cols})")
        for r in reader:
            text = (r.get(text_col) or "").strip()
            if not text:
                continue
            rows.append({
                "text": text,
                "gloss": (r.get(gloss_col) or "").strip(),
                "review": (r.get(review_col) or "").strip(),
            })
    return rows


def _parse_all(raw_responses: list[str]):
    """Parseia cada resposta; None onde falhou. Devolve (decisions, errors)."""
    decisions = []
    errors = []
    for raw in raw_responses:
        try:
            decisions.append(parse_judge_response(raw))
            errors.append(None)
        except JudgeParseError as exc:
            decisions.append(None)
            errors.append(str(exc))
    return decisions, errors


def _generate_thinking_off(llm, prompts: list[str], chunk: int) -> list[str]:
    """Gera com thinking DESLIGADO e teto de tokens baixo, reusando o mesmo
    modelo já carregado (troca temporária de config; não recarrega pesos)."""
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


def _make_accessible(directory: Path) -> None:
    """chmod recursivo: dir 0777, arquivos 0666 (o container é root; sem isso o
    usuário do host não consegue editar/apagar o que foi gerado)."""
    try:
        os.chmod(directory, 0o777)
        for path in directory.rglob("*"):
            os.chmod(path, 0o777 if path.is_dir() else 0o666)
    except PermissionError:
        pass


def main() -> None:
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    io = cfg["io"]

    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=Path(io["input"]))
    p.add_argument("--exp-name", type=str, default="",
                   help="nome do experimento; default: <data>_thinking-on")
    p.add_argument("--limit", type=int, default=None, help="processa só as N primeiras linhas")
    args = p.parse_args()

    pairs = read_pairs(
        args.input,
        text_col=io.get("text_col", "Input"),
        gloss_col=io.get("gloss_col", "Output"),
        review_col=io.get("review_col", "Output review"),
    )
    if args.limit is not None:
        pairs = pairs[: args.limit]
    print(f"carregadas {len(pairs)} linhas de {args.input}")

    # pasta do experimento
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    name = args.exp_name.strip() or f"{stamp}_thinking-on"
    exp_dir = Path(io.get("experiments_dir", "framework_rules/experiments")) / name
    exp_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(CONFIG_PATH, exp_dir / "config.yaml")   # snapshot dos parâmetros

    # base de regras + prompts
    rules_text = load_rules_text()
    known_ids = valid_rule_ids()
    prompt_config = load_prompt_config()
    prompts = [
        build_judge_prompt(prompt_config, text=pr["text"], gloss=pr["gloss"], rules=rules_text)
        for pr in pairs
    ]

    # inferência (passo 1: thinking ligado)
    llm = get_llm()
    chunk = int(cfg.get("batch_size", 4))
    raw_responses = generate_batch(llm, prompts, chunk=chunk)
    decisions, errors = _parse_all(raw_responses)

    # rede de segurança: qualquer resposta que não parseou (thinking estourou o
    # teto de tokens sem fechar o JSON) é reprocessada com thinking DESLIGADO —
    # JSON compacto que sempre fecha — reusando o MESMO modelo já na GPU.
    fallback_idx = [i for i, d in enumerate(decisions) if d is None]
    if fallback_idx:
        print(f"reprocessando {len(fallback_idx)} resposta(s) sem parse com thinking OFF...")
        retry_raw = _generate_thinking_off(llm, [prompts[i] for i in fallback_idx], chunk)
        for i, raw in zip(fallback_idx, retry_raw):
            raw_responses[i] = raw
            try:
                decisions[i] = parse_judge_response(raw)
                errors[i] = None
            except JudgeParseError as exc:
                errors[i] = str(exc)

    # parse + escrita
    csv_path = exp_dir / "teste_inicial.csv"
    raw_path = exp_dir / "raw.jsonl"
    counts = {"Sim": 0, "Não": 0}
    parse_failed = 0
    unknown_rule_hits = 0
    fallback_used = len(fallback_idx)

    with csv_path.open("w", newline="", encoding="utf-8") as out_fh, \
         raw_path.open("w", encoding="utf-8") as raw_fh:
        writer = csv.writer(out_fh)
        writer.writerow(["Texto", "Glosa", "Correto?", "Regras", "Sugestao", "Glosa Review"])

        for i, (pr, raw) in enumerate(zip(pairs, raw_responses)):
            correto = regras = sugestao = ""
            decision = decisions[i]
            if decision is not None:
                correto = decision.correto
                regras = "; ".join(decision.regras)
                sugestao = decision.sugestao
                counts[correto] += 1
                if any(rid not in known_ids for rid in decision.regras):
                    unknown_rule_hits += 1
            else:
                parse_failed += 1

            writer.writerow([pr["text"], pr["gloss"], correto, regras, sugestao, pr["review"]])
            raw_fh.write(json.dumps(
                {"text": pr["text"], "gloss": pr["gloss"], "raw": raw,
                 "parse_error": errors[i], "fallback": i in fallback_idx},
                ensure_ascii=False,
            ) + "\n")

    meta = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "model": cfg["model"]["name"],
        "generation": cfg.get("generation", {}),
        "input": str(args.input),
        "rules_file": str(RULES_PATH),
        "prompt_file": str(PROMPT_PATH),
        "n_rows": len(pairs),
        "correto_sim": counts["Sim"],
        "correto_nao": counts["Não"],
        "parse_failed": parse_failed,
        "fallback_thinking_off": fallback_used,
        "rows_citing_unknown_rule": unknown_rule_hits,
    }
    (exp_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # o container roda como root: libera escrita para o usuário do host poder
    # abrir/editar/deletar os arquivos gerados.
    _make_accessible(exp_dir)

    print(f"escrito {csv_path}")
    print(f"  Sim={counts['Sim']}  Não={counts['Não']}  "
          f"parse_failed={parse_failed}  fallback_thinking_off={fallback_used}")
    if unknown_rule_hits:
        print(f"  ATENÇÃO: {unknown_rule_hits} linha(s) citaram ID de regra fora da base")


if __name__ == "__main__":
    main()
