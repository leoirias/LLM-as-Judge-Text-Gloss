"""Carrega um prompt YAML (fragmentos @{...} / variáveis {{...}}) num
PromptConfig e o renderiza. Reusa o renderizador do repo (src/judge/prompt.py).
Requer PYTHONPATH=src.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from judge.prompt import render_prompt_template
from models.base import PromptConfig

_KNOWN = {"objective", "instructions", "output_rules", "template"}


def load_prompt_config(path: Path) -> PromptConfig:
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


def render(prompt_config: PromptConfig, variables: dict[str, Any]) -> str:
    return render_prompt_template(prompt_config, variables)
