"""Triagem de tópicos (passo 2): decide, pelo TÍTULO, se o tópico entra na extração.

Automático e genérico: nada é declarado por livro. Cada título distinto do
`manifest.csv` vai ao modelo, que responde {"incluir": bool, "motivo": str}.
O resultado é escrito de volta no manifesto, nas colunas `incluir` e
`motivo_exclusao` — auditável e editável à mão depois.

Por que só o título: é barato. Descarta-se um tópico inteiro (às vezes 15
trechos) com uma chamada curta, em vez de ler o texto todo para depois jogar
fora. O prompt manda incluir na dúvida — excluir um tópico útil perde as
regras dele para sempre; incluir um inútil custa uma chamada.

Rodar (dentro do container, GPU do projeto):
    docker compose exec -e CUDA_VISIBLE_DEVICES=<N> judge bash -lc \
      'PYTHONPATH=src /opt/venv/bin/python libras_pipeline/extraction/triagem_topicos.py --book gramatica'
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

import yaml
from tqdm import tqdm

from llm import get_llm
from parsing import extract_json
from prompt import load_prompt_config, render

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.yaml"
PROMPT_PATH = HERE / "prompts" / "triagem_topicos.yaml"

COLS = ["n", "arquivo", "topico", "nivel_outline", "pagina_ini", "pagina_fim",
        "n_paginas", "n_topicos", "parte", "tokens", "topicos_todos",
        "incluir", "motivo_exclusao"]

# Títulos que não dizem nada sobre o assunto: placeholder do passo 1 e rótulos
# de outline raso. Julgar só por eles é decidir no escuro — nesses casos vai
# junto um trecho do texto.
SEM_INFO = re.compile(r"^(\(início da faixa\)|cap[_\s-]*\d+|cap[íi]tulo\s+\d+|"
                      r"conclus[ãa]o|introdu[çc][ãa]o|sum[áa]rio)\.?$", re.I)


def _titulos(linha: dict) -> list[str]:
    """Todos os tópicos de um trecho. `topicos_todos` existe desde a correção
    do agrupamento; manifesto antigo cai para o `topico` sozinho."""
    bruto = (linha.get("topicos_todos") or "").strip()
    return [x.strip() for x in bruto.split("|") if x.strip()] or [linha["topico"]]


def _amostra(caminho: Path, n=300) -> str:
    """Primeiras linhas do corpo do trecho, sem o cabeçalho nem os [p.N]."""
    try:
        txt = caminho.read_text(encoding="utf-8")
    except OSError:
        return ""
    corpo = re.sub(r"^===.*$|^\[p\.\d+\]$", "", txt, flags=re.M)
    return " ".join(corpo.split())[:n]


def _decide(raw: str) -> tuple[int, str]:
    """Parse tolerante: qualquer resposta ilegível vira INCLUIR.

    O default seguro é incluir — uma triagem que falha silenciosamente não
    pode ser a causa de um tópico sumir da extração.
    """
    try:
        obj = extract_json(raw)
        if isinstance(obj, list):
            obj = obj[0]
        incluir = obj.get("incluir")
        if isinstance(incluir, str):
            incluir = incluir.strip().lower() in ("true", "1", "sim", "yes")
        if incluir is None:
            return 1, ""
        motivo = str(obj.get("motivo", "") or "").strip()
        return (1, "") if incluir else (0, motivo or "excluído pela triagem")
    except Exception:
        return 1, ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", help="filtra a fonte pelo label/slug no config")
    ap.add_argument("--chunks-dir", default=str(HERE / "chunks"))
    ap.add_argument("--batch", type=int, default=8, help="títulos por batch no modelo")
    args = ap.parse_args()

    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    livros = [b for b in cfg["books"]
              if not args.book or args.book.lower() in (b["label"] + " " + b["slug"]).lower()]
    if not livros:
        raise SystemExit(f"nenhuma fonte casa com --book {args.book!r}")

    prompt_config = load_prompt_config(PROMPT_PATH)
    llm = get_llm()

    for b in livros:
        manifesto = Path(args.chunks_dir) / b["slug"] / "manifest.csv"
        if not manifesto.exists():
            print(f"[{b['slug']}] sem manifest.csv — rode chunk_topicos.py antes")
            continue

        with manifesto.open(newline="", encoding="utf-8") as fh:
            linhas = list(csv.DictReader(fh))

        # Um tópico pode ocupar vários trechos (parte 1/n) e um trecho pode
        # agrupar vários tópicos: decide 1 vez por TÍTULO, não por trecho.
        titulos, amostras = [], {}
        for l in linhas:
            for tit in _titulos(l):
                if tit not in amostras:
                    titulos.append(tit)
                    amostras[tit] = (_amostra(manifesto.parent / l["arquivo"])
                                     if SEM_INFO.match(tit.strip()) else "")
        cegos = sum(1 for t in titulos if amostras[t])
        print(f"[{b['slug']}] {len(titulos)} títulos distintos em {len(linhas)} trechos"
              + (f" ({cegos} sem título informativo -> vão com trecho do texto)" if cegos else ""))

        decisoes: dict[str, tuple[int, str]] = {}
        for i in tqdm(range(0, len(titulos), args.batch), desc=b["slug"], unit="batch"):
            lote = titulos[i:i + args.batch]
            prompts = [render(prompt_config, {"titulo": t + (f"\n  TRECHO INICIAL: {amostras[t]}"
                                                             if amostras[t] else "")})
                       for t in lote]
            for titulo, raw in zip(lote, llm.generate_batch(prompts)):
                decisoes[titulo] = _decide(raw)

        for l in linhas:
            ds = [decisoes.get(t, (1, "")) for t in _titulos(l)]
            # Só exclui o trecho se TODOS os tópicos dele foram reprovados —
            # senão um tópico bom sairia carregado por um vizinho reprovado.
            if all(d[0] == 0 for d in ds):
                l["incluir"] = 0
                l["motivo_exclusao"] = " ; ".join(dict.fromkeys(d[1] for d in ds if d[1]))
            else:
                l["incluir"], l["motivo_exclusao"] = 1, ""

        with manifesto.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=COLS)
            w.writeheader()
            for l in linhas:
                w.writerow({c: l.get(c, "") for c in COLS})

        fora = [l for l in linhas if str(l["incluir"]) == "0"]
        tf = sum(int(l["tokens"]) for l in fora)
        tt = sum(int(l["tokens"]) for l in linhas)
        print(f"  entram: {len(linhas) - len(fora)} trechos | "
              f"excluídos: {len(fora)} ({100 * tf // max(tt, 1)}% dos tokens)")
        for t in titulos:
            inc, motivo = decisoes.get(t, (1, ""))
            if not inc:
                print(f"    [fora] {t[:58]:<58} — {motivo[:44]}")
        print(f"  manifesto atualizado: {manifesto}")


if __name__ == "__main__":
    main()
