"""Remove bloco <think> (se existir) e extrai o JSON da resposta do modelo.

O modelo de extração roda com thinking desligado (ver config.yaml), mas o
strip fica como rede de segurança caso o template do modelo ainda emita algo
parecido.
"""

from __future__ import annotations

import json
import re
from typing import Any

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_thinking(reply: str) -> str:
    text = _THINK_BLOCK.sub("", reply or "")
    if "<think>" in text:  # <think> aberto sem fechar (estourou tokens)
        text = text.split("</think>")[-1] if "</think>" in text else ""
    return text.strip()


def extract_json(reply: str) -> Any:
    text = strip_thinking(reply).replace("```json", "```")
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError(f"nenhum JSON encontrado na resposta: {text[:200]!r}")
    start = min(starts)
    ends = [i for i in (text.rfind("}"), text.rfind("]")) if i != -1]
    end = max(ends)
    # strict=False: tolera caractere de controle cru (ex.: \t) dentro de uma
    # string JSON, algo que o modelo às vezes emite sem escapar, mesmo quando
    # o resto do documento está bem formado.
    return json.loads(text[start : end + 1], strict=False)
