"""Etapa 2 (parte 2): funde candidatas duplicadas do grupo voice2sign dentro
de cada categoria, com justificativa, chegando numa lista final.

Processa em RODADAS por categoria (padrão "reduce"/refine): pega a lista já
consolidada (vazia na 1a rodada) + um lote novo de candidatas
(`lote_tamanho` no config.yaml), pede pro modelo devolver a lista
consolidada ATUALIZADA (funde o que for duplicata, mantém o resto como
estava). Isso evita mandar uma categoria inteira (ex.: sintaxe do ASL tem
112 candidatas) numa chamada só — mesmo problema de estouro já visto na
etapa 1. Categoria com só 1 candidata nem chama o modelo, vira final direto.

Se uma rodada falhar o parse (ou um item da resposta vier com campo
faltando), degrada com segurança: a(s) candidata(s) afetada(s) entra(m) na
lista SEM checar fusão (cada uma vira uma entrada própria) em vez de serem
perdidas — fica registrado no log pra revisão manual. Cada resposta crua do
modelo é salva em `<output>.raw.txt` (auditoria/recuperação manual, já que
esse script — diferente de `extract.py` — ainda não sabe reconstruir sem
chamar o modelo de novo).

`--categoria X` reprocessa só 1 categoria e faz merge no CSV final já
existente (troca só as linhas daquela categoria, preserva as outras) — NÃO
sobrescreve o arquivo inteiro.

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


def _dedupe_ids_origem(rules: list[MergedRule]) -> list[MergedRule]:
    """Rede de segurança: em rodadas com muitas candidatas, o modelo às
    vezes reivindica a MESMA candidata de origem em mais de 1 regra final
    (visto acontecer na prática — ~1-9% das candidatas em algumas
    categorias). Mantém a candidata só na PRIMEIRA regra que a reivindicar
    (na ordem em que a lista consolidada foi devolvida) e remove das
    seguintes; também tira repetição dentro da mesma lista ids_origem de uma
    regra só. Se uma regra ficar sem nenhum id_origem (toda a origem dela já
    foi reivindicada antes), ela é descartada — é puramente redundante."""
    seen: set[str] = set()
    out: list[MergedRule] = []
    for r in rules:
        kept = [i for i in dict.fromkeys(r.ids_origem) if i not in seen]  # dedup preservando ordem
        seen.update(kept)
        if not kept:
            continue
        out.append(r.model_copy(update={"ids_origem": kept}))
    return out


def merge_categoria(categoria: str, rows: list[dict], prompt_config, llm, lote: int,
                     raw_log: Path | None = None) -> list[MergedRule]:
    if len(rows) == 1:
        return [_standalone(rows[0])]

    by_id = {r["id"]: r for r in rows}
    consolidado: list[MergedRule] = []
    expected_ids: set[str] = set()

    for chunk in tqdm(_chunks(rows, lote), desc=f"merge {categoria}", unit="lote"):
        expected_ids.update(r["id"] for r in chunk)
        prompt = render(prompt_config, {
            "categoria": categoria,
            "consolidado": _consolidated_block(consolidado),
            "novas": _candidate_block(chunk),
        })
        raw = llm.generate(prompt)
        if raw_log is not None:
            with raw_log.open("a", encoding="utf-8") as fh:
                fh.write(f"### {categoria} lote {len(expected_ids) // lote}\n{raw}\n\n")
        try:
            data = extract_json(raw)
            items = data["regras_finais"]
        except (ValueError, KeyError, TypeError) as exc:
            print(f"    [{categoria}] lote falhou o parse (JSON), entrando sem checar fusão ({exc})")
            novo_consolidado = list(consolidado) + [_standalone(r) for r in chunk]
        else:
            # valida item por item, não a lista inteira de uma vez — 1 item
            # com campo faltando não pode derrubar as outras regras boas da
            # mesma resposta (mesmo problema já corrigido em extract.py).
            novo_consolidado = []
            for i, item in enumerate(items):
                try:
                    novo_consolidado.append(MergedRule.model_validate(item))
                except ValidationError as exc:
                    first = exc.errors()[0]
                    print(f"    [{categoria}] item #{i} da resposta descartado (schema): "
                          f"{first['msg']} em {first['loc']}")

        # rede de segurança: garante que TODA candidata já vista até agora
        # (não só as desta rodada) segue coberta na lista devolvida — o
        # modelo pode esquecer uma candidata nova, OU um item de rodada
        # anterior pode ter vindo com schema inválido nesta resposta e sido
        # descartado acima, derrubando junto uma regra já consolidada.
        covered_now = {i for m in novo_consolidado for i in m.ids_origem}
        esquecidas = sorted(expected_ids - covered_now)
        if esquecidas:
            print(f"    [{categoria}] {len(esquecidas)} candidata(s) sumiram na rodada, "
                  f"devolvendo como entrada própria: {esquecidas}")
            novo_consolidado.extend(_standalone(by_id[mid]) for mid in esquecidas)

        consolidado = novo_consolidado
    return _dedupe_ids_origem(consolidado)


def _standalone(r: dict) -> MergedRule:
    """Embrulha 1 candidata da etapa 1 como regra final própria, sem fusão —
    usado nos dois casos em que não dá pra confiar na fusão do modelo (round
    falhou o parse, ou o modelo esqueceu a candidata na resposta)."""
    return MergedRule(titulo=r["titulo"], descricao=r["descricao"], gatilho=r["gatilho"],
                       exemplos=[e.strip() for e in r["exemplos"].split(";") if e.strip()],
                       ids_origem=[r["id"]], justificativa_fusao="")


def _fontes_por_id(rows: list[dict]) -> dict[str, str]:
    return {r["id"]: f"{r['fonte_livro']} p.{r['fonte_pagina']}" for r in rows}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--categoria", type=str, default=None,
                    help="processa só esta categoria (default: todas)")
    p.add_argument("--group", type=str, default="voice2sign", choices=["voice2sign", "sign2voice"],
                    help="qual grupo fundir (default: voice2sign)")
    p.add_argument("--source", type=str, default=None,
                    help="funde as candidatas de UMA fonte isolada "
                         "(<source>_<group>_candidatas.csv -> <source>_<group>_final.csv)")
    p.add_argument("--id-prefix", type=str, default=None,
                    help="sobrescreve o id_prefix do config (ex.: TANIA), pra IDs de fontes "
                         "diferentes não colidirem quando as bases forem unidas")
    args = p.parse_args()

    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    id_prefix = args.id_prefix or cfg["id_prefix"]
    lote = int(cfg.get("lote_tamanho", 15))
    pre = f"{args.source}_" if args.source else ""
    in_path = HERE / "output" / f"{pre}{args.group}_candidatas.csv"
    out_path = HERE / "output" / f"{pre}{args.group}_final.csv"
    if not in_path.exists():
        raise SystemExit(f"{in_path} não existe — rode classify_pipeline.py"
                          + (f" --source {args.source}" if args.source else "") + " primeiro")

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

    # se --categoria foi usado, preserva as OUTRAS categorias que já estavam
    # no CSV final (senão reprocessar 1 categoria apaga o resto do arquivo —
    # bug real que já aconteceu aqui).
    final_rows: list[dict] = []
    if args.categoria and out_path.exists():
        with out_path.open(newline="", encoding="utf-8") as fh:
            final_rows = [r for r in csv.DictReader(fh) if r["categoria"] != args.categoria]

    raw_log = out_path.with_suffix(".raw.txt")
    if not args.categoria:
        raw_log.write_text("", encoding="utf-8")  # rodada completa começa um log novo

    for categoria, cat_rows in groups.items():
        merged = merge_categoria(categoria, cat_rows, prompt_config, llm, lote, raw_log=raw_log)
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
