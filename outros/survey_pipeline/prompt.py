"""Renderizador de prompt self-contained (fragmentos @{...} + variáveis {{...}}).

Deliberadamente NÃO importa de src/judge para evitar colisão de nome com o
arquivo judge.py deste pacote. Mesma convenção usada no resto do repo.
"""

from __future__ import annotations

import re
from pathlib import Path
from string import Template
from typing import Any

import yaml

_INLINE = re.compile(r"@\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_VAR = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def load_prompt(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def render(prompt: dict, variables: dict[str, Any]) -> str:
    template = str(prompt["template"])

    # 1) inline dos fragmentos @{chave} usando as chaves string do YAML
    fragments = {k: str(v) for k, v in prompt.items() if isinstance(v, str)}

    def _inline(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in fragments:
            raise KeyError(f"fragmento de prompt desconhecido: {key!r}")
        return fragments[key].strip()

    template = _INLINE.sub(_inline, template)

    # 2) variáveis {{var}} -> substituição segura
    normalized = _VAR.sub(lambda m: f"${m.group(1)}", template)
    values = {k: "" if v is None else str(v) for k, v in variables.items()}
    return Template(normalized).substitute(values).strip()
