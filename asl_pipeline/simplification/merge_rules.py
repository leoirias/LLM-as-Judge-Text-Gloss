"""Etapa 2 (parte 2): funde candidatas duplicadas do grupo voice2sign dentro
de cada categoria, com justificativa, chegando numa lista final.

Processa em RODADAS por categoria (padrão "reduce"/refine): pega a lista já
consolidada (vazia na 1a rodada) + um lote novo de candidatas
(`lote_tamanho` no config.yaml), pede pro modelo devolver a lista
consolidada ATUALIZADA (funde o que for duplicata, mantém o resto como
estava). Isso evita mandar uma categoria inteira (ex.: sintaxe do ASL tem
112 candidatas) numa chamada só — mesmo problema de estouro já visto na
etapa 1. Categoria com só 1 candidata nem chama o modelo, vira final direto.

Se uma rodada falhar o parse, degrada com segurança: as candidatas daquele
lote entram na lista SEM checar fusão (cada uma vira uma entrada própria) em
vez de serem perdidas — fica registrado no log pra revisão manual.

Rodar (dentro do container, GPU do projeto):
    docker compose exec -e CUDA_VISIBLE_DEVICES=<N> judge bash -lc \
      'PYTHONPATH=src uv run python asl_pipeline/simplification/merge_rules.py'
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import Counter, defaultdict
from pathlib import Path

import yaml
from pydantic import ValidationError
from tqdm import tqdm

from llm import get_llm
from parsing import extract_json
from prompt import load_prompt_config, render
from schema import MergedRule

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.yaml"
PROMPT_PATH = HERE / "prompts" / "merge_rules.yaml"

OUT_COLS = ["id", "categoria", "titulo", "descricao", "gatilho", "exemplos",
            "ids_origem", "justificativa_fusao", "fontes"]


def _chmod(path: Path) -> None:
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass


def _load_candidates(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _group_by_categoria(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r["categoria"]].append(r)
    return groups


def _candidate_block(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        lines.append(f"[{r['id']}] {r['titulo']}")
        lines.append(f"  descricao: {r['descricao']}")
        lines.append(f"  gatilho: {r['gatilho']}")
        if r["exemplos"]:
            lines.append(f"  exemplos: {r['exemplos']}")
    return "\n".join(lines)


def _consolidated_block(rules: list[MergedRule]) -> str:
    if not rules:
        return "(vazio — primeira rodada)"
    lines = []
    for i, r in enumerate(rules):
        lines.append(f"[{i}] {r.titulo}  (ids_origem: {', '.join(r.ids_origem)})")
        lines.append(f"  descricao: {r.descricao}")
        lines.append(f"  gatilho: {r.gatilho}")
        if r.exemplos:
            lines.append(f"  exemplos: {'; '.join(r.exemplos)}")
    return "\n".join(lines)


def _chunks(rows: list[dict], size: int) -> list[list[dict]]:
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def merge_categoria(categoria: str, rows: list[dict], prompt_config, llm, lote: int) -> list[MergedRule]:
    if len(rows) == 1:
        r = rows[0]
        return [MergedRule(titulo=r["titulo"], descricao=r["descricao"], gatilho=r["gatilho"],
                            exemplos=[e.strip() for e in r["exemplos"].split(";") if e.strip()],
                            ids_origem=[r["id"]], justificativa_fusao="")]

    consolidado: list[MergedRule] = []
    for chunk in tqdm(_chunks(rows, lote), desc=f"merge {categoria}", unit="lote"):
        prompt = render(prompt_config, {
            "categoria": categoria,
            "consolidado": _consolidated_block(consolidado),
            "novas": _candidate_block(chunk),
        })
        raw = llm.generate(prompt)
        try:
            data = extract_json(raw)
            novo_consolidado = [MergedRule.model_validate(item) for item in data["regras_finais"]]
        except (ValueError, KeyError, ValidationError, TypeError) as exc:
            print(f"    [{categoria}] lote falhou o parse, entrando sem checar fusão ({exc})")
            novo_consolidado = list(consolidado) + [
                MergedRule(titulo=r["titulo"], descricao=r["descricao"], gatilho=r["gatilho"],
                           exemplos=[e.strip() for e in r["exemplos"].split(";") if e.strip()],
                           ids_origem=[r["id"]], justificativa_fusao="")
                for r in chunk
            ]
        consolidado = novo_consolidado
    return consolidado


def _fontes_por_id(rows: list[dict]) -> dict[str, str]:
    return {r["id"]: f"{r['fonte_livro']} p.{r['fonte_pagina']}" for r in rows}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--categoria", type=str, default=None,
                    help="processa só esta categoria (default: todas)")
    args = p.parse_args()

    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    id_prefix = cfg["id_prefix"]
    lote = int(cfg.get("lote_tamanho", 15))
    in_path = HERE / cfg["io"]["input"]
    out_path = HERE / cfg["io"]["output"]

    rows = _load_candidates(in_path)
    fontes = _fontes_por_id(rows)
    groups = _group_by_categoria(rows)
    if args.categoria:
        groups = {k: v for k, v in groups.items() if k == args.categoria}
        if not groups:
            raise SystemExit(f"categoria {args.categoria!r} não encontrada em {in_path}")

    print(f"{len(rows)} candidatas em {len(groups)} categoria(s)")

    prompt_config = load_prompt_config(PROMPT_PATH)
    llm = get_llm()

    final_rows: list[dict] = []
    for categoria, cat_rows in groups.items():
        merged = merge_categoria(categoria, cat_rows, prompt_config, llm, lote)
        counters: Counter[str] = Counter()
        for m in merged:
            counters[categoria] += 1
            final_id = f"{id_prefix}.{categoria.upper()}.{counters[categoria]}"
            origem_fontes = "; ".join(sorted({fontes.get(i, i) for i in m.ids_origem}))
            final_rows.append({
                "id": final_id,
                "categoria": categoria,
                "titulo": m.titulo,
                "descricao": m.descricao,
                "gatilho": m.gatilho,
                "exemplos": " ; ".join(m.exemplos),
                "ids_origem": " ; ".join(m.ids_origem),
                "justificativa_fusao": m.justificativa_fusao,
                "fontes": origem_fontes,
            })
        print(f"  {categoria}: {len(cat_rows)} candidatas -> {len(merged)} regra(s) final(is)")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLS)
        w.writeheader()
        w.writerows(final_rows)
    _chmod(out_path)
    print(f"\nescrito {out_path} ({len(final_rows)} regras finais de {len(rows)} candidatas)")


if __name__ == "__main__":
    main()
