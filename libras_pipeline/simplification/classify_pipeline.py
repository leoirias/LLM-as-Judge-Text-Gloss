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

Por padrão não usa modelo/GPU — é só reorganização determinística das colunas
que a extração já preencheu.

Com `--confirmar`, faz uma SEGUNDA OPINIÃO sobre o canal: pergunta ao modelo,
regra por regra e sem o texto do livro, se ela é mesmo verificável só no
texto. Serve de rede contra erro da extração, que decide esse campo junto com
outros sete numa resposta só. Divergência entre as duas decisões nunca é
silenciosa — vai para `divergencias_canal.csv` e para as colunas
`canal_extracao` / `canal_confirmado` / `divergencia` do CSV de saída.

`--source X` restringe aos CSVs de extração cujo nome bate com X (ex.:
`--source tania`) e escreve em arquivo SEPARADO (`<source>_voice2sign_
candidatas.csv`), sem tocar no pool principal — útil quando se quer isolar
uma fonte nova pra comparar contra a base já consolidada (etapa 3), em vez
de já misturar tudo de uma vez.

Rodar (sem GPU, direto):
    python asl_pipeline/simplification/classify_pipeline.py
    python asl_pipeline/simplification/classify_pipeline.py --source tania
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
EXTRACTION_OUTPUT = HERE.parent / "extraction" / "output"
OUTPUT_DIR = HERE / "output"

IN_COLS = ["id", "categoria", "titulo", "descricao", "gatilho",
           "verificavel_por_texto", "exemplos", "fonte_livro",
           "fonte_pagina", "fonte_citacao"]
OUT_COLS = ["pipeline", *IN_COLS]
CONF_COLS = ["pipeline", *IN_COLS, "canal_extracao", "canal_confirmado",
             "divergencia", "motivo_confirmacao"]
PROMPT_PATH = HERE / "prompts" / "confirmar_canal.yaml"


def _chmod(path: Path) -> None:
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass


def _to_bool(v: str) -> bool:
    return str(v).strip().lower() in ("true", "1", "sim", "yes")


def _confirma_canal(rows: list[dict], politica: str, batch: int) -> list[dict]:
    """Segunda opinião do modelo sobre `verificavel_por_texto`, regra a regra.

    A pergunta é feita sozinha — sem o texto do livro e sem os outros campos —
    justamente para não repetir o contexto que pode ter enviesado a extração.

    Política em caso de divergência:
      conservadora  qualquer 'false' das duas decisões manda a regra para
                    sign2voice. É o default porque os dois erros não custam
                    igual: uma regra não-verificável que passa faz o juiz
                    reprovar glosa correta; uma verificável que sai só reduz
                    cobertura (o juiz abstém, que é honesto).
      confirmacao   a segunda opinião decide sozinha.
    """
    from tqdm import tqdm

    from llm import get_llm
    from parsing import extract_json
    from prompt import load_prompt_config, render

    prompt_config = load_prompt_config(PROMPT_PATH)
    llm = get_llm()

    prompts = [render(prompt_config, {"titulo": r.get("titulo", ""),
                                      "descricao": r.get("descricao", ""),
                                      "gatilho": r.get("gatilho", ""),
                                      "exemplos": r.get("exemplos", "") or "(sem exemplos)"})
               for r in rows]
    respostas: list[str] = []
    for i in tqdm(range(0, len(prompts), batch), desc="confirmando canal", unit="batch"):
        respostas.extend(llm.generate_batch(prompts[i:i + batch]))

    for row, raw in zip(rows, respostas):
        antes = _to_bool(row["verificavel_por_texto"])
        try:
            obj = extract_json(raw)
            if isinstance(obj, list):
                obj = obj[0]
            conf = obj.get("verificavel_por_texto")
            if isinstance(conf, str):
                conf = _to_bool(conf)
            motivo = str(obj.get("motivo", "") or "").strip()
            if conf is None:
                raise ValueError("sem campo verificavel_por_texto")
        except Exception:
            # parse falhou: mantém a decisão da extração, marcado como tal
            conf, motivo = antes, "parse da confirmação falhou; mantida a extração"

        depois = antes and conf if politica == "conservadora" else conf
        row["canal_extracao"] = "voice2sign" if antes else "sign2voice"
        row["canal_confirmado"] = "voice2sign" if conf else "sign2voice"
        row["divergencia"] = "sim" if antes != conf else ""
        row["motivo_confirmacao"] = motivo
        row["verificavel_por_texto"] = str(bool(depois)).lower()
    return rows


def _dedupe_ids(rows: list[dict]) -> list[dict]:
    """Cada CSV de livro numera suas próprias regras a partir de 1 por
    categoria (`extract.py` reinicia o contador por livro) — então, ao
    concatenar 2+ livros aqui, é possível 2 livros diferentes produzirem o
    mesmo ID (ex.: os 2 livros de Libras cada um gerando o próprio
    "LIBRAS.SINTAXE.002"). Renumera só a(s) categoria(s) que realmente
    colidiu(ram); categoria sem colisão mantém o ID original."""
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cat[r["categoria"]].append(r)

    out: list[dict] = []
    for categoria, cat_rows in by_cat.items():
        ids = [r["id"] for r in cat_rows]
        if len(set(ids)) == len(ids):
            out.extend(cat_rows)
            continue
        prefix = cat_rows[0]["id"].split(".")[0]
        for i, r in enumerate(cat_rows, start=1):
            out.append({**r, "id": f"{prefix}.{categoria.upper()}.{i:03d}"})
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=str, default=None,
                    help="processa só o(s) CSV(s) de extração cujo nome contém esse texto; "
                         "escreve em arquivo separado, não mexe no pool principal")
    p.add_argument("--from-dir", type=str, default=None,
                    help="diretório de extração a ler (default: extraction/output). "
                         "Use extraction/output_topicos para a extração por tópico")
    p.add_argument("--out-dir", type=str, default=None,
                    help="diretório de saída (default: simplification/output). Use um nome "
                         "novo pra não sobrescrever a base atual")
    p.add_argument("--confirmar", action="store_true",
                    help="segunda opinião do modelo sobre o canal de cada regra (usa GPU)")
    p.add_argument("--politica", choices=("conservadora", "confirmacao"), default="conservadora",
                    help="o que vale quando as duas decisões divergem (default: conservadora)")
    p.add_argument("--batch", type=int, default=8, help="regras por batch no modelo")
    args = p.parse_args()

    global EXTRACTION_OUTPUT, OUTPUT_DIR
    if args.from_dir:
        d = Path(args.from_dir)
        # nome simples ("output_topicos") resolve dentro de extraction/, que é
        # onde ficam as saídas do passo 3; caminho com barra resolve a partir
        # da raiz do pipeline.
        EXTRACTION_OUTPUT = (d if d.is_absolute()
                             else HERE.parent / ("extraction" if len(d.parts) == 1 else "") / d)
    if args.out_dir:
        OUTPUT_DIR = Path(args.out_dir) if Path(args.out_dir).is_absolute() else HERE / args.out_dir
    print(f"lendo   {EXTRACTION_OUTPUT}")
    print(f"escrevendo {OUTPUT_DIR}")

    csvs = sorted(EXTRACTION_OUTPUT.glob("*_regras.csv"))
    if args.source:
        csvs = [c for c in csvs if args.source.lower() in c.name.lower()]
        if not csvs:
            raise SystemExit(f"nenhum CSV de extração bate com --source {args.source!r} em {EXTRACTION_OUTPUT}")
    elif not csvs:
        raise SystemExit(f"nenhum CSV encontrado em {EXTRACTION_OUTPUT} — "
                          f"rode a extração (etapa 1) primeiro")

    todas: list[dict] = []
    for path in csvs:
        with path.open(newline="", encoding="utf-8") as fh:
            todas.extend(dict(row) for row in csv.DictReader(fh))

    prefix = f"{args.source}_" if args.source else ""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.confirmar:
        print(f"segunda opinião sobre o canal de {len(todas)} regras "
              f"(política: {args.politica})")
        todas = _confirma_canal(todas, args.politica, args.batch)

    voice2sign: list[dict] = []
    sign2voice: list[dict] = []
    for row in todas:
        pipeline = "voice2sign" if _to_bool(row["verificavel_por_texto"]) else "sign2voice"
        (voice2sign if pipeline == "voice2sign" else sign2voice).append({"pipeline": pipeline, **row})
    voice2sign, sign2voice = _dedupe_ids(voice2sign), _dedupe_ids(sign2voice)

    if args.confirmar:
        # Relatório escrito DEPOIS do _dedupe_ids: antes, o `id` daqui era o de
        # pré-renumeração e não casava com o do CSV final. Carrega também
        # titulo/descricao, pra não depender de join por id — que é ambíguo
        # justamente nos casos que a renumeração existe para resolver.
        div = [r for r in voice2sign + sign2voice if r.get("divergencia") == "sim"]
        rel = OUTPUT_DIR / f"{prefix}divergencias_canal.csv"
        cols_div = ["id", "titulo", "descricao", "canal_extracao", "canal_confirmado",
                    "motivo_confirmacao", "fonte_livro"]
        with rel.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols_div)
            w.writeheader()
            w.writerows([{c: r.get(c, "") for c in cols_div} for r in div])
        _chmod(rel)
        print(f"  divergências: {len(div)}/{len(todas)} "
              f"({100 * len(div) // max(len(todas), 1)}%) -> {rel}")
        for r in div[:12]:
            print(f"    [{r.get('id','')}] {r.get('titulo','')[:52]:<52} "
                  f"{r['canal_extracao']} -> {r['canal_confirmado']}")

    cols = CONF_COLS if args.confirmar else OUT_COLS
    for name, rows in [(f"{prefix}voice2sign_candidatas.csv", voice2sign),
                        (f"{prefix}sign2voice_candidatas.csv", sign2voice)]:
        out = OUTPUT_DIR / name
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows([{c: r.get(c, "") for c in cols} for r in rows])
        _chmod(out)
        print(f"escrito {out} ({len(rows)} regras)")

    total = len(voice2sign) + len(sign2voice)
    if total:
        print(f"\ntotal: {total} regras | voice2sign: {len(voice2sign)} "
              f"({100 * len(voice2sign) / total:.0f}%) | sign2voice: {len(sign2voice)} "
              f"({100 * len(sign2voice) / total:.0f}%)")


if __name__ == "__main__":
    main()
