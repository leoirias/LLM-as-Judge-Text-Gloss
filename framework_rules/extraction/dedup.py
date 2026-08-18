"""Deduplicação das regras extraídas do livro inteiro.

Cada janela de páginas é extraída isoladamente, então o mesmo fenômeno reaparece
várias vezes (ex.: "Formação de perguntas sim/não" saiu 9x). Este passo agrupa
regras equivalentes e funde cada grupo numa regra canônica, preservando TODAS as
páginas de origem — o nº de ocorrências vira, inclusive, sinal de força da
evidência (regra que reaparece em 9 páginas do livro é bem estabelecida).

Não usa GPU: agrupamento por similaridade de título/descrição (determinístico).

Rodar (dentro do container; NÃO precisa de GPU):

    docker compose exec judge bash -lc '
      PYTHONPATH=src uv run python framework_rules/extraction/dedup.py'
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import yaml

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.yaml"

# limiares de agrupamento (conservadores: na dúvida, NÃO funde)
T_TITULO = 0.82          # títulos quase iguais -> mesma regra
T_TITULO_FRACO = 0.60    # título parecido ...
T_DESCRICAO = 0.72       # ... + descrição parecida -> mesma regra

OUT_COLS = ["id", "categoria", "titulo", "descricao", "gatilho", "verificavel_por_texto",
            "exemplos", "fonte_pagina", "fonte_paginas", "ocorrencias", "fonte_citacao"]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _cluster(rows: list[dict]) -> list[list[int]]:
    titulos = [_norm(r.get("titulo", "")) for r in rows]
    descs = [_norm(r.get("descricao", ""))[:300] for r in rows]
    n = len(rows)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            ts = _sim(titulos[i], titulos[j])
            ds = _sim(descs[i], descs[j])
            if ts >= T_TITULO or (ts >= T_TITULO_FRACO and ds >= T_DESCRICAO):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _merge(rows: list[dict], idxs: list[int], new_id: str) -> dict:
    """Funde um grupo: mantém a versão mais rica e acumula a procedência."""
    members = [rows[i] for i in idxs]
    best = max(members, key=lambda r: len(r.get("descricao", "")))

    paginas: list[str] = []
    exemplos: list[str] = []
    for m in members:
        p = (m.get("fonte_pagina") or "").strip()
        if p and p not in paginas:
            paginas.append(p)
        for ex in (m.get("exemplos") or "").split(" ; "):
            ex = ex.strip()
            if ex and ex not in exemplos:
                exemplos.append(ex)
    paginas.sort(key=lambda x: int(x) if x.lstrip("-").isdigit() else 10**9)

    # se QUALQUER ocorrência foi marcada não-verificável no texto, mantém False:
    # o extrator erra para "True" com muito mais frequência que o contrário.
    verif = "False" if any(
        str(m.get("verificavel_por_texto", "")).strip().lower() == "false" for m in members
    ) else "True"

    return {
        "id": new_id,
        "categoria": best.get("categoria", ""),
        "titulo": best.get("titulo", ""),
        "descricao": best.get("descricao", ""),
        "gatilho": best.get("gatilho", ""),
        "verificavel_por_texto": verif,
        "exemplos": " ; ".join(exemplos),
        "fonte_pagina": paginas[0] if paginas else "",
        "fonte_paginas": " ; ".join(paginas),
        "ocorrencias": len(members),
        "fonte_citacao": best.get("fonte_citacao", ""),
    }


def main() -> None:
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    io = cfg["io"]

    p = argparse.ArgumentParser()
    p.add_argument("--rules", type=Path, default=Path(io["full_rules_out"]))
    p.add_argument("--out", type=Path, default=Path(io["full_dedup_out"]))
    args = p.parse_args()

    rows = list(csv.DictReader(args.rules.open(encoding="utf-8")))
    groups = _cluster(rows)
    groups.sort(key=lambda g: min(g))  # mantém a ordem original do livro

    merged = [_merge(rows, g, f"ASLFD.{n:03d}") for n, g in enumerate(groups, start=1)]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLS)
        w.writeheader()
        w.writerows(merged)
    try:
        os.chmod(args.out, 0o666)
    except OSError:
        pass

    dups = [g for g in groups if len(g) > 1]
    print(f"{len(rows)} regras -> {len(merged)} únicas "
          f"({sum(len(g) - 1 for g in dups)} redundantes em {len(dups)} grupos)")
    for g in sorted(dups, key=len, reverse=True)[:10]:
        print(f'  {len(g)}x  "{rows[g[0]].get("titulo","")}"')
    print(f"escrito {args.out}")


if __name__ == "__main__":
    main()
