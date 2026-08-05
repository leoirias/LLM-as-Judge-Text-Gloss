"""Resíduo LLM (etapa Verify-LLM): carrega o pacote, monta o bloco de regras
Voice2Sign e o prompt de cada par. O parse fica em parsing.py.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from prompt import load_prompt, render

HERE = Path(__file__).parent
PROMPT_PATH = HERE / "prompts" / "judge.yaml"


def load_package(path: Path | str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def voice2sign_rules(package: dict) -> list[dict]:
    """Só as regras que ESTE validador usa (texto->glosa)."""
    return [r for r in package.get("rules", []) if r.get("pipeline") == "voice2sign"]


def render_rules(rules: list[dict]) -> str:
    blocos = []
    for r in rules:
        linha = f"[{r['id']}] ({r.get('categoria','')}) {r.get('descricao','')}"
        if r.get("exemplos"):
            linha += f"\n    ex.: {r['exemplos'][0]}"
        blocos.append(linha)
    return "\n".join(blocos)


def _render_grammar(g: dict) -> str:
    """Renderiza uma gramática (Libras: produções + léxico + decisões)."""
    linhas = ["PRODUÇÕES (regras de montar a frase):"]
    for p in g.get("producoes_consolidadas", []):
        linhas.append(f"  {p}")
    linhas.append("\nLÉXICO (classe de cada sinal):")
    for it in g.get("lexico", []):
        extra = f" — {it['atributo_libras']}" if it.get("atributo_libras") else ""
        linhas.append(f"  {it['sinal']}: {it.get('classe','')}{extra}")
    linhas.append("\nDECISÕES da consultoria:")
    for d in g.get("decisoes", []):
        linhas.append(f"  - {d}")
    return "\n".join(linhas)


def build_rules_text(source: dict) -> str:
    """Detecta o formato do pacote e renderiza o bloco de regras do prompt:
    - gramática (Libras): tem `producoes_consolidadas`;
    - pacote plano (ASL): tem `rules` com campo `pipeline`."""
    if "producoes_consolidadas" in source:
        return _render_grammar(source)
    return render_rules(voice2sign_rules(source))


def count_rules(source: dict) -> int:
    if "producoes_consolidadas" in source:
        return len(source.get("producoes_consolidadas", []))
    return len(voice2sign_rules(source))


def build_prompt(prompt_dict: dict, text: str, gloss: str, rules_text: str,
                 achados: str = "nenhum") -> str:
    return render(prompt_dict, {
        "regras": rules_text,
        "achados": achados,
        "text": text,
        "gloss": gloss,
    })


def load_judge_prompt() -> dict:
    return load_prompt(PROMPT_PATH)
