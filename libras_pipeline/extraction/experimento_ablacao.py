"""Ablação: separa o efeito do PROMPT, do FATIAMENTO e da TRIAGEM.

As três mudanças entraram na mesma rodada, então nenhuma comparação feita até
agora atribui causa. Este experimento muda UMA variável por vez:

    A  prompt antigo    + janela de 15 páginas     output/               (já existe)
    B  prompt corrigido + janela de 15 páginas     output_exp_b_janela/  14 chamadas
    C  prompt corrigido + trechos por tópico       output_exp_c_topico/  63 chamadas
    D  prompt corrigido + tópico + triagem         output_exp_d_triado/  0 chamadas

    A -> B   isola o PROMPT       (só o prompt mudou)
    B -> C   isola o FATIAMENTO   (só o corte mudou)
    C -> D   isola a TRIAGEM      (só o descarte de tópicos mudou)

D não gasta GPU: como a extração é determinística e cada trecho é uma chamada
isolada, D é exatamente o subconjunto de C nos trechos que a triagem aprovou.
`--derivar` recorta o *.raw.txt de C; o CSV sai depois com `extract.py --from-raw`.

Uso:
    python experimento_ablacao.py --derivar        # monta o raw de D a partir de C
    python experimento_ablacao.py --comparar       # imprime a escada
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
SLUG = "libras_gramatica_cap5"
MARCA = re.compile(r"^### p\.(\d+)-(\d+)$", re.M)

CELULAS = [
    ("A", "output",              "prompt antigo    + janela 15p"),
    ("B", "output_exp_b_janela", "prompt corrigido + janela 15p"),
    ("C", "output_exp_c_topico", "prompt corrigido + por tópico"),
    ("D", "output_exp_d_triado", "prompt corrigido + tópico + triagem"),
]

ALVOS = {
    "idiomatismo":    ["idiom", "expressão idiomática", "expressao idiomatica"],
    "ordem/SVO":      ["ordem", "svo", "sov", "osv"],
    "preposição":     ["preposi"],
    "negação":        ["negaç", "negac"],
    "verbo modal":    ["modal"],
}


def _ler(d: str) -> list[dict] | None:
    p = HERE / d / f"{SLUG}_regras.csv"
    if not p.exists():
        return None
    with p.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _trechos_no_raw(d: str) -> int:
    p = HERE / d / f"{SLUG}_regras.raw.txt"
    return len(MARCA.findall(p.read_text(encoding="utf-8"))) if p.exists() else 0


def _v2s(rows: list[dict]) -> int:
    return sum(1 for r in rows
               if str(r.get("verificavel_por_texto", "")).strip().lower() in ("true", "1", "sim"))


def _bate(r: dict, termos: list[str]) -> bool:
    blob = " ".join(r.get(c, "") for c in ("titulo", "descricao", "gatilho", "categoria")).lower()
    return any(t in blob for t in termos)


def derivar() -> None:
    """Recorta o raw de C, mantendo só os trechos aprovados pela triagem."""
    origem = HERE / "output_exp_c_topico" / f"{SLUG}_regras.raw.txt"
    if not origem.exists():
        raise SystemExit(f"falta a célula C: {origem}\n"
                         f"rode a extração com --chunks --no-triagem primeiro")

    manifesto = HERE / "chunks" / SLUG / "manifest.csv"
    with manifesto.open(newline="", encoding="utf-8") as fh:
        aprovados = {(int(r["pagina_ini"]), int(r["pagina_fim"]))
                     for r in csv.DictReader(fh) if r.get("incluir", "1").strip() != "0"}

    texto = origem.read_text(encoding="utf-8")
    partes = MARCA.split(texto)
    blocos = [(int(partes[i]), int(partes[i + 1]), partes[i + 2].strip())
              for i in range(1, len(partes), 3)]
    mantidos = [b for b in blocos if (b[0], b[1]) in aprovados]

    destino = HERE / "output_exp_d_triado"
    destino.mkdir(parents=True, exist_ok=True)
    saida = destino / f"{SLUG}_regras.raw.txt"
    saida.write_text("\n\n".join(f"### p.{a}-{b}\n{r}" for a, b, r in mantidos), encoding="utf-8")

    print(f"C tinha {len(blocos)} trechos; a triagem aprova {len(aprovados)}")
    print(f"D recortado com {len(mantidos)} trechos -> {saida}")
    print(f"\nagora gere o CSV de D (sem GPU):")
    print(f"  python extract.py --book gramatica --from-raw --out-dir output_exp_d_triado")


def comparar() -> None:
    dados = {}
    for k, d, rot in CELULAS:
        rows = _ler(d)
        if rows is None:
            print(f"[{k}] ainda não rodou ({d}/)")
            continue
        dados[k] = {"rows": rows, "rot": rot, "trechos": _trechos_no_raw(d)}

    print("=" * 88)
    print("CÉLULAS")
    print("=" * 88)
    print(f"{'':<3} {'configuração':<38} {'trechos':>8} {'regras':>7} {'v2s':>5} {'%v2s':>6} {'págs':>5}")
    for k, _, _ in CELULAS:
        if k not in dados:
            continue
        r, t = dados[k]["rows"], dados[k]["trechos"]
        v = _v2s(r)
        pg = len({x.get("fonte_pagina", "") for x in r if x.get("fonte_pagina", "").strip()})
        print(f"{k:<3} {dados[k]['rot']:<38} {t:>8} {len(r):>7} {v:>5} "
              f"{100*v//max(len(r),1):>5}% {pg:>5}")

    print()
    print("=" * 88)
    print("O QUE CADA COMPARAÇÃO ISOLA")
    print("=" * 88)
    for a, b, nome in (("A", "B", "PROMPT"), ("B", "C", "FATIAMENTO"), ("C", "D", "TRIAGEM")):
        if a not in dados or b not in dados:
            print(f"\n{a} -> {b}  ({nome}): incompleto")
            continue
        ra, rb = dados[a]["rows"], dados[b]["rows"]
        va, vb = _v2s(ra), _v2s(rb)
        print(f"\n{a} -> {b}   isola o efeito do/da {nome}")
        print(f"   regras      {len(ra):>4} -> {len(rb):<4} ({len(rb)-len(ra):+d})")
        print(f"   voice2sign  {va:>4} -> {vb:<4} ({vb-va:+d})   <- o que importa para o juiz")
        print(f"   chamadas    {dados[a]['trechos']:>4} -> {dados[b]['trechos']:<4}")
        for nm, termos in ALVOS.items():
            na = sum(1 for r in ra if _bate(r, termos))
            nb = sum(1 for r in rb if _bate(r, termos))
            if na or nb:
                print(f"     {nm:<14} {na:>3} -> {nb:<3} ({nb-na:+d})")

    if "D" in dados:
        print()
        print("=" * 88)
        print("CATEGORIAS NA CÉLULA FINAL (D)")
        print("=" * 88)
        print("  ", dict(Counter(r["categoria"] for r in dados["D"]["rows"]).most_common()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--derivar", action="store_true", help="monta o raw da célula D a partir de C")
    ap.add_argument("--comparar", action="store_true", help="imprime a escada de comparações")
    args = ap.parse_args()
    if args.derivar:
        derivar()
    if args.comparar or not args.derivar:
        comparar()


if __name__ == "__main__":
    main()
