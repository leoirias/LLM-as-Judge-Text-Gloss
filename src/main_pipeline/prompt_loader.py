"""Load + render a prompt YAML (same format as src/models/prompts).

YAML has string fields (objective, instructions, output_rules, examples, ...)
plus a `template`. In the template:
  @{field}   inlines another field from the same YAML
  {{var}}    substitutes a runtime variable (text, gloss, few_shot, ...)
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_INLINE = re.compile(r"@\{([a-zA-Z_]\w*)\}")
_VAR = re.compile(r"\{\{\s*([a-zA-Z_]\w*)\s*\}\}")


@lru_cache(maxsize=None)
def load(path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def render(data: dict[str, Any], variables: dict[str, str]) -> str:
    fields = {k: v for k, v in data.items() if isinstance(v, str)}
    text = data.get("template", "")
    for _ in range(5):  # resolve nested @{...} inlines
        if not _INLINE.search(text):
            break
        text = _INLINE.sub(lambda m: fields.get(m.group(1), m.group(0)), text)
    text = _VAR.sub(lambda m: str(variables.get(m.group(1), m.group(0))), text)
    return text.strip()
