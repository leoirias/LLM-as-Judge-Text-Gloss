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
from schema import Decisao, MergedRule

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


def _aplica(consolidado: list[MergedRule], chunk: list[dict],
            decisoes: list[Decisao], by_id: dict[str, dict]) -> list[MergedRule]:
    """Aplica as decisões do modelo à lista consolidada, em código.

    O modelo devolve só o que fazer com cada candidata nova; quem monta a
    lista é aqui. Assim a resposta tem tamanho fixo (~1 decisão por
    candidata), em vez de crescer com a base — que era o que estourava o
    limite de tokens e truncava o JSON no meio.

    Em duas passadas porque uma candidata pode mandar fundir com OUTRA do
    mesmo lote que ainda não foi colocada (referência para frente): a 1ª
    passada coloca quem não depende de irmão, a 2ª resolve o resto, repetindo
    enquanto houver progresso (cobre cadeia A->B->C).
    """
    por_decisao = {d.id_origem: d for d in decisoes}
    onde = {i: n for n, r in enumerate(consolidado) for i in r.ids_origem}
    ids_lote = {c["id"] for c in chunk}

    def alvo_de(cid: str):
        d = por_decisao.get(cid)
        if d is None or not d.funde_com.strip():
            return None, d
        ref = d.funde_com.strip().strip("[]")
        if ref.isdigit() and int(ref) < len(consolidado):
            return int(ref), d                 # índice da lista consolidada
        return onde.get(ref), d                # id de outra candidata (None se ainda não posta)

    def coloca(cand: dict, alvo, d) -> None:
        cid = cand["id"]
        if alvo is None:
            nova = _standalone(cand)
            if d is not None:
                nova = nova.model_copy(update={
                    "titulo": d.titulo or nova.titulo,
                    "descricao": d.descricao or nova.descricao,
                    "gatilho": d.gatilho or nova.gatilho,
                    "exemplos": d.exemplos or nova.exemplos,
                })
            consolidado.append(nova)
            onde[cid] = len(consolidado) - 1
        else:
            r = consolidado[alvo]
            exemplos = list(dict.fromkeys([*r.exemplos, *((d.exemplos if d else []) or []),
                                           *_exemplos_da_candidata(cand)]))
            consolidado[alvo] = r.model_copy(update={
                "titulo": (d.titulo if d else "") or r.titulo,
                "descricao": (d.descricao if d else "") or r.descricao,
                "gatilho": (d.gatilho if d else "") or r.gatilho,
                "exemplos": exemplos,
                "ids_origem": [*r.ids_origem, cid],
                "justificativa_fusao": (d.justificativa_fusao if d else "") or r.justificativa_fusao,
            })
            onde[cid] = alvo

    pendentes = []
    for cand in chunk:                                   # 1ª passada
        d = por_decisao.get(cand["id"])
        ref = (d.funde_com.strip().strip("[]") if d and d.funde_com.strip() else "")
        if ref and ref in ids_lote and ref not in onde:  # depende de irmão ainda não posto
            pendentes.append(cand)
            continue
        alvo, d = alvo_de(cand["id"])
        coloca(cand, alvo, d)

    while pendentes:                                     # 2ª passada, até parar de progredir
        restantes = []
        for cand in pendentes:
            alvo, d = alvo_de(cand["id"])
            if alvo is None and (d and d.funde_com.strip()):
                restantes.append(cand)                   # alvo ainda não existe
            else:
                coloca(cand, alvo, d)
        if len(restantes) == len(pendentes):             # ciclo ou referência quebrada
            for cand in restantes:
                coloca(cand, None, por_decisao.get(cand["id"]))
            break
        pendentes = restantes
    return consolidado


def _exemplos_da_candidata(cand: dict) -> list[str]:
    return [e.strip() for e in (cand.get("exemplos") or "").split(";") if e.strip()]


def merge_categoria(categoria: str, rows: list[dict], prompt_config, llm, lote: int,
                     raw_log: Path | None = None) -> list[MergedRule]:
    if len(rows) == 1:
        return [_standalone(rows[0])]

    by_id = {r["id"]: r for r in rows}
    consolidado: list[MergedRule] = []
    expected_ids: set[str] = set()

    for n_lote, chunk in enumerate(tqdm(_chunks(rows, lote), desc=f"merge {categoria}",
                                        unit="lote"), 1):
        expected_ids.update(r["id"] for r in chunk)
        prompt = render(prompt_config, {
            "categoria": categoria,
            "consolidado": _consolidated_block(consolidado),
            "novas": _candidate_block(chunk),
        })
        raw = llm.generate(prompt)
        if raw_log is not None:
            with raw_log.open("a", encoding="utf-8") as fh:
                fh.write(f"### {categoria} lote {n_lote}\n{raw}\n\n")

        decisoes: list[Decisao] = []
        try:
            data = extract_json(raw)
            items = data["decisoes"]
        except (ValueError, KeyError, TypeError) as exc:
            print(f"    [{categoria}] lote {n_lote}: parse falhou, candidatas entram "
                  f"sem checar fusão ({exc})")
            items = []
        for i, item in enumerate(items):
            try:
                decisoes.append(Decisao.model_validate(item))
            except ValidationError as exc:
                first = exc.errors()[0]
                print(f"    [{categoria}] decisão #{i} descartada (schema): "
                      f"{first['msg']} em {first['loc']}")

        faltando = {r["id"] for r in chunk} - {d.id_origem for d in decisoes}
        if faltando:
            print(f"    [{categoria}] lote {n_lote}: {len(faltando)} candidata(s) sem "
                  f"decisão, entram como regra própria")

        consolidado = _aplica(consolidado, chunk, decisoes, by_id)

        # rede de segurança: nenhuma candidata já vista pode ter sumido
        covered = {i for m in consolidado for i in m.ids_origem}
        esquecidas = sorted(expected_ids - covered)
        if esquecidas:
            print(f"    [{categoria}] {len(esquecidas)} candidata(s) sumiram, "
                  f"devolvendo como entrada própria: {esquecidas}")
            consolidado.extend(_standalone(by_id[mid]) for mid in esquecidas)

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
    p.add_argument("--from-dir", type=str, default=None,
                    help="diretório com os *_candidatas.csv (default: simplification/output)")
    p.add_argument("--out-dir", type=str, default=None,
                    help="diretório de saída (default: o mesmo de --from-dir)")
    p.add_argument("--id-prefix", type=str, default=None,
                    help="sobrescreve o id_prefix do config (ex.: TANIA), pra IDs de fontes "
                         "diferentes não colidirem quando as bases forem unidas")
    args = p.parse_args()

    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    id_prefix = args.id_prefix or cfg["id_prefix"]
    lote = int(cfg.get("lote_tamanho", 15))
    pre = f"{args.source}_" if args.source else ""
    base_in = HERE / "output"
    if args.from_dir:
        d = Path(args.from_dir)
        base_in = d if d.is_absolute() else HERE / d
    base_out = base_in if not args.out_dir else (
        Path(args.out_dir) if Path(args.out_dir).is_absolute() else HERE / args.out_dir)
    base_out.mkdir(parents=True, exist_ok=True)
    in_path = base_in / f"{pre}{args.group}_candidatas.csv"
    out_path = base_out / f"{pre}{args.group}_final.csv"
    print(f"lendo   {in_path}")
    print(f"escrevendo {out_path}")
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
