"""CLI do juiz (etapa 3): texto + glosa -> valido/invalido/nao_coberto,
citando regras por ID real da base construída nas etapas 1-2.

Nome do arquivo é `run.py`, não `judge.py`, de propósito: `judge.py` colide
com o pacote `src/judge/` (usado por `prompt.py` pra renderizar templates) —
com PYTHONPATH=src, um arquivo local `judge.py` sombrearia o pacote de
verdade e quebraria o import.

Salva a resposta crua de cada frase em output/resultado.raw.txt (auditoria/
diagnóstico, mesmo padrão já usado em extraction/simplification).

Rodar (dentro do container, GPU do projeto):
    docker compose exec -e CUDA_VISIBLE_DEVICES=<N> judge bash -lc \
      'PYTHONPATH=src uv run python libras_pipeline/evaluation/run.py'
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

from tqdm import tqdm

from llm import get_llm
from parsing import JudgeParseError, parse_verdict
from prompt import load_prompt_config, render
from rules_store import load_rules_text, valid_rule_ids
from schema import JudgeVerdict

HERE = Path(__file__).parent
PROMPT_PATH = HERE / "prompts" / "judge.yaml"
DATA_PATH = HERE / "data" / "frases_teste.csv"
OUT_PATH = HERE / "output" / "resultado.csv"
RAW_PATH = HERE / "output" / "resultado.raw.txt"

CSV_COLS = ["Texto", "Glosa", "Estado", "Fidelidade", "Naturalidade", "Regras",
            "Problema", "Sugestao", "Esperado", "Acertou", "Origem"]


def _chmod(path: Path) -> None:
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass


def _load_pairs(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--rules", type=Path, default=None,
                    help="CSV da base de regras a usar (default: simplification/output/"
                         "voice2sign_final.csv). Permite comparar bases diferentes.")
    p.add_argument("--prompt", type=Path, default=None,
                    help="YAML do prompt a usar (default: prompts/judge.yaml). "
                         "Permite comparar versões de prompt sem trocar arquivo.")
    p.add_argument("--exp-name", type=str, default="",
                    help="sufixo do arquivo de saída: output/resultado_<exp-name>.csv "
                         "(sem isso, sobrescreve resultado.csv)")
    args = p.parse_args()

    global OUT_PATH, RAW_PATH
    if args.exp_name:
        OUT_PATH = HERE / "output" / f"resultado_{args.exp_name}.csv"
        RAW_PATH = HERE / "output" / f"resultado_{args.exp_name}.raw.txt"

    pairs = _load_pairs(DATA_PATH)
    kw = {"path": args.rules} if args.rules else {}
    rules_text = load_rules_text(**kw)
    ids_validos = valid_rule_ids(**kw)
    fonte = args.rules.name if args.rules else "voice2sign_final.csv"
    print(f"{len(pairs)} frases de teste | base: {fonte} ({len(ids_validos)} regras)")

    caminho_prompt = args.prompt or PROMPT_PATH
    if not caminho_prompt.is_absolute():
        caminho_prompt = caminho_prompt if caminho_prompt.exists() else HERE / caminho_prompt
    print(f"prompt: {caminho_prompt.name}")
    prompt_config = load_prompt_config(caminho_prompt)
    llm = get_llm()

    rows_out = []
    counts: dict[str, int] = {}
    acertos, avaliados = 0, 0
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_text("", encoding="utf-8")  # log novo a cada rodada

    for pr in tqdm(pairs, desc="Julgando", unit="frase"):
        prompt = render(prompt_config, {"regras": rules_text, "text": pr["text"], "gloss": pr["gloss"]})
        raw = llm.generate(prompt)
        with RAW_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"### {pr['text']} -> {pr['gloss']}\n{raw}\n\n")
        try:
            v = parse_verdict(raw)
            origem = "llm"
        except JudgeParseError as exc:
            v = JudgeVerdict(veredito="nao_coberto", problema=f"resposta não parseável: {exc}")
            origem = "parse_falhou"

        # regras citadas que não existem na base = sinal de alucinação de ID
        regras_invalidas = [r for r in v.regras if r not in ids_validos]
        if regras_invalidas:
            print(f"  aviso: citou ID(s) inexistente(s) na base: {regras_invalidas}")

        counts[v.veredito] = counts.get(v.veredito, 0) + 1
        esperado = pr.get("esperado", "").strip()
        acertou = ""
        if esperado and v.veredito != "nao_coberto":
            avaliados += 1
            acertou = "sim" if v.veredito == esperado else "não"
            if acertou == "sim":
                acertos += 1

        rows_out.append({
            "Texto": pr["text"], "Glosa": pr["gloss"], "Estado": v.veredito,
            "Fidelidade": v.representa_sentido, "Naturalidade": v.natural_estrutura,
            "Regras": "; ".join(v.regras), "Problema": v.problema, "Sugestao": v.sugestao,
            "Esperado": esperado, "Acertou": acertou, "Origem": origem,
        })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLS)
        w.writeheader()
        w.writerows(rows_out)
    _chmod(OUT_PATH)

    print(f"\nescrito {OUT_PATH}")
    print(f"estados: {counts}")
    taxa_abstencao = counts.get("nao_coberto", 0) / len(pairs)
    print(f"taxa de abstenção (nao_coberto): {taxa_abstencao:.0%}")
    if avaliados:
        print(f"acurácia vs esperado (só nos não-abstidos, {avaliados}/{len(pairs)}): {acertos}/{avaliados} = {acertos/avaliados:.0%}")


if __name__ == "__main__":
    main()
