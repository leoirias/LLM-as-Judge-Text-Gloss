"""CLI de extração (etapa 1 do fluxo: doc -> regras candidatas em CSV).

Sem argumentos: roda TODOS os livros de `books:` no config.yaml, em janelas
de página, sequencialmente, salvando o *.raw.txt de cada livro conforme
avança — pensado pra disparar 1 comando e deixar rodando sem supervisão
(ex.: hora do almoço).

`id` é atribuído pelo próprio script (sequencial por categoria, ex.:
ASLFD.VERBOS.003), não pedido ao modelo — ver schema.py.

Rodar (dentro do container, GPU do projeto):
    docker compose exec -e CUDA_VISIBLE_DEVICES=<N> judge bash -lc \
      'PYTHONPATH=src uv run python asl_pipeline/extraction/extract.py'

Um livro só:                  --book "<trecho do label>"
Reconstruir sem chamar o modelo (usa o *.raw.txt já salvo): --from-raw

Reprocessar só janelas específicas que falharam (ex.: truncamento ou aspas
mal-formadas que o parser não recupera sozinho) — funde no *.raw.txt e no
CSV existentes, sem tocar nas janelas boas:
    extract.py --book "<trecho do label>" --patch-pages 16 30 --patch-pages 61 75
"""

from __future__ import annotations

import argparse
import csv
import os
import re
from collections import Counter
from pathlib import Path

import yaml
from pydantic import ValidationError
from tqdm import tqdm

from llm import get_llm
from parsing import extract_json
from pdf_text import extract_pages
from prompt import load_prompt_config, render
from schema import ExtractedRule

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
CONFIG_PATH = HERE / "config.yaml"
PROMPT_PATH = HERE / "prompts" / "extract_rules.yaml"
OUTPUT_DIR = HERE / "output"

CSV_COLS = ["id", "categoria", "titulo", "descricao", "gatilho",
            "verificavel_por_texto", "exemplos", "fonte_livro",
            "fonte_pagina", "fonte_citacao"]

_WINDOW_MARK = re.compile(r"^### p\.(\d+)-(\d+)$", re.MULTILINE)


def _chmod(path: Path) -> None:
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass


def _windows(start: int, end: int, size: int) -> list[tuple[int, int]]:
    return [(s, min(s + size - 1, end)) for s in range(start, end + 1, size)]


def _parse_rules(raw: str) -> list[ExtractedRule]:
    """Valida regra por regra, não a lista inteira de uma vez: se 1 regra na
    janela tiver um campo faltando/errado, descarta só ela — não derruba as
    outras N-1 regras boas da mesma janela junto (o que a validação atômica
    de `ExtractedRuleSet.model_validate` faria)."""
    data = extract_json(raw)
    if not isinstance(data, dict) or "rules" not in data:
        raise ValueError(f"resposta sem campo 'rules': {str(data)[:200]!r}")
    rules: list[ExtractedRule] = []
    for i, item in enumerate(data["rules"]):
        try:
            rules.append(ExtractedRule.model_validate(item))
        except ValidationError as exc:
            first = exc.errors()[0]
            print(f"    regra #{i} descartada (schema): {first['msg']} em {first['loc']}")
    return rules


def _assign_ids(rules: list[ExtractedRule], id_prefix: str, categorias_validas: set[str]) -> None:
    """ID determinístico por categoria (ex.: ASLFD.VERBOS.003). O modelo só
    escolhe `categoria`; cada janela é uma chamada de LLM independente sem
    memória das IDs usadas nas janelas anteriores, então o ID não pode vir
    do modelo sem risco de colisão."""
    counters: Counter[str] = Counter()
    for r in rules:
        cat = r.categoria.strip().lower()
        if cat not in categorias_validas:
            cat = "outros"
        counters[cat] += 1
        r.id = f"{id_prefix}.{cat.upper()}.{counters[cat]:03d}"


def _write_csv(rules: list[ExtractedRule], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
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
                "fonte_livro": r.fonte_livro,
                "fonte_pagina": r.fonte_pagina,
                "fonte_citacao": r.fonte_citacao,
            })
    _chmod(out)


def _raw_chunks_from_file(raw_path: Path) -> list[tuple[int, int, str]]:
    """Recorta o *.raw.txt salvo de volta em (start, end, raw) por janela."""
    text = raw_path.read_text(encoding="utf-8")
    parts = _WINDOW_MARK.split(text)
    chunks = []
    for i in range(1, len(parts), 3):
        s, e, raw = int(parts[i]), int(parts[i + 1]), parts[i + 2].strip()
        chunks.append((s, e, raw))
    return chunks


def _finalize(label: str, slug: str, chunks: list[tuple[int, int, str]],
              id_prefix: str, categorias_validas: set[str]) -> None:
    """Parseia todas as janelas (regra por regra, ver _parse_rules), atribui
    IDs e escreve o CSV final do livro. Único ponto que gera o CSV — usado
    tanto pela rodada normal/--from-raw quanto pelo --patch-pages, pra IDs
    ficarem sempre recalculados de forma consistente sobre o conjunto
    completo de janelas (antigas boas + novas remendadas)."""
    out = OUTPUT_DIR / f"{slug}_regras.csv"
    all_rules: list[ExtractedRule] = []
    failed = 0
    for s, e, raw in chunks:
        try:
            rules = _parse_rules(raw)
        except (ValueError, ValidationError) as exc:
            failed += 1
            print(f"  janela p.{s}-{e}: parse falhou, pulada ({exc})")
            continue
        for r in rules:
            r.fonte_livro = label
        all_rules.extend(rules)

    _assign_ids(all_rules, id_prefix, categorias_validas)
    _write_csv(all_rules, out)
    msg = f"  escrito {out} ({len(all_rules)} regras"
    if failed:
        msg += f", {failed} janela(s) c/ falha de parse"
    print(msg + ")")


def _run_book(book: dict, cfg: dict, prompt_config, llm, *, from_raw: bool) -> None:
    label = book["label"]
    raw_path = OUTPUT_DIR / f"{book['slug']}_regras.raw.txt"
    id_prefix = cfg["id_prefix"]
    categorias_validas = {c.lower() for c in cfg.get("categorias_validas", [])}

    if from_raw:
        if not raw_path.exists():
            print(f"[{label}] sem *.raw.txt salvo, pulando (rode sem --from-raw primeiro)")
            return
        chunks = _raw_chunks_from_file(raw_path)
        print(f"[{label}] reconstruindo CSV de {raw_path} ({len(chunks)} janelas, sem GPU)")
    else:
        pdf = ROOT / book["path"]
        windows = _windows(int(book["start_page"]), int(book["end_page"]), int(book.get("window_pages", 15)))
        print(f"[{label}] {pdf.name} p.{book['start_page']}-{book['end_page']} ({len(windows)} janelas)")
        chunks = []
        for s, e in tqdm(windows, desc=label, unit="janela"):
            text = extract_pages(pdf, s, e)
            raw = llm.generate(render(prompt_config, {"chapter_text": text}))
            chunks.append((s, e, raw))
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text("\n\n".join(f"### p.{s}-{e}\n{r}" for s, e, r in chunks), encoding="utf-8")
        _chmod(raw_path)

    _finalize(label, book["slug"], chunks, id_prefix, categorias_validas)


def _patch_book(book: dict, cfg: dict, prompt_config, llm, ranges: list[list[int]]) -> None:
    """Reprocessa só as faixas de página em `ranges` (respeitando o
    `window_pages` do livro), funde no *.raw.txt existente (substitui janelas
    antigas na mesma faixa exata, mantém as outras) e reescreve o CSV a
    partir do conjunto completo — sem gastar GPU nas janelas que já estavam
    boas."""
    label = book["label"]
    raw_path = OUTPUT_DIR / f"{book['slug']}_regras.raw.txt"
    id_prefix = cfg["id_prefix"]
    categorias_validas = {c.lower() for c in cfg.get("categorias_validas", [])}

    win_size = int(book.get("window_pages", 15))
    patch_windows: list[tuple[int, int]] = []
    for start, end in ranges:
        patch_windows.extend(_windows(int(start), int(end), win_size))

    pdf = ROOT / book["path"]
    print(f"[{label}] reprocessando {len(patch_windows)} janela(s): {patch_windows}")
    new_chunks: list[tuple[int, int, str]] = []
    for s, e in tqdm(patch_windows, desc=f"{label} (patch)", unit="janela"):
        text = extract_pages(pdf, s, e)
        raw = llm.generate(render(prompt_config, {"chapter_text": text}))
        new_chunks.append((s, e, raw))

    old_chunks = _raw_chunks_from_file(raw_path) if raw_path.exists() else []
    patched_ranges = {(s, e) for s, e in patch_windows}
    kept = [c for c in old_chunks if (c[0], c[1]) not in patched_ranges]
    all_chunks = kept + new_chunks

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("\n\n".join(f"### p.{s}-{e}\n{r}" for s, e, r in all_chunks), encoding="utf-8")
    _chmod(raw_path)

    _finalize(label, book["slug"], all_chunks, id_prefix, categorias_validas)


def main() -> None:
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    p = argparse.ArgumentParser()
    p.add_argument("--book", type=str, default=None,
                    help="roda só o(s) livro(s) cujo label contém esse texto")
    p.add_argument("--from-raw", action="store_true",
                    help="reconstrói o(s) CSV(s) do *.raw.txt já salvo, sem chamar o modelo")
    p.add_argument("--patch-pages", action="append", nargs=2, type=int, metavar=("START", "END"),
                    help="reprocessa só esta faixa de páginas (repita a flag pra várias faixas); "
                         "exige --book resolvendo a exatamente 1 livro; funde no raw.txt/CSV existentes")
    args = p.parse_args()

    books = cfg["books"]
    if args.book:
        books = [b for b in books if args.book.lower() in b["label"].lower()]
        if not books:
            raise SystemExit(f"nenhum livro em books: bate com --book {args.book!r}")

    prompt_config = load_prompt_config(PROMPT_PATH)

    if args.patch_pages:
        if len(books) != 1:
            raise SystemExit(f"--patch-pages exige --book resolvendo a exatamente 1 livro "
                              f"(bateu com {len(books)})")
        llm = get_llm()
        _patch_book(books[0], cfg, prompt_config, llm, ranges=args.patch_pages)
        return

    llm = None if args.from_raw else get_llm()
    for book in books:
        _run_book(book, cfg, prompt_config, llm, from_raw=args.from_raw)


if __name__ == "__main__":
    main()
