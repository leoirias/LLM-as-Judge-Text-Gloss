"""Carrega o prompt do juiz (prompts/judge_rules.yaml) e o renderiza.

Reusa o renderizador de fragmentos `@{...}` / variáveis `{{...}}` do repo
(src/judge/prompt.py) — mesma convenção do resto do projeto. Requer
PYTHONPATH=src.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from judge.prompt import render_prompt_template  # PYTHONPATH=src
from models.base import PromptConfig

PROMPT_PATH = Path(__file__).parent / "prompts" / "judge_rules.yaml"

_KNOWN = {"objective", "instructions", "output_rules", "template"}


def load_prompt_config(path: Path = PROMPT_PATH) -> PromptConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    extra = {k: v for k, v in data.items() if k not in _KNOWN and k != "name"}
    return PromptConfig(
        name=str(data.get("name", path.stem)),
        template=str(data["template"]),
        objective=str(data.get("objective", "")),
        instructions=str(data.get("instructions", "")),
        output_rules=str(data.get("output_rules", "")),
        extra=extra,
    )


def build_judge_prompt(
    prompt_config: PromptConfig, text: str, gloss: str, rules: str
) -> str:
    return render_prompt_template(
        prompt_config,
        variables={"text": text, "gloss": gloss, "rules": rules},
    )
