"""Parsing das respostas do modelo: remove o bloco <think> do Qwen3 e extrai o
JSON (objeto ou lista) do texto restante, tolerando preâmbulo/cercas."""

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
    return json.loads(text[start : end + 1])
