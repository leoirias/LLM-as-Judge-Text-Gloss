"""Reply parsing helpers: strip a Qwen3 <think> block, then pull the JSON
object out of whatever text remains (tolerating preamble/fences)."""

from __future__ import annotations

import json
import re
from typing import Any

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_thinking(reply: str) -> str:
    return _THINK_BLOCK.sub("", reply or "").strip()


def extract_json(reply: str) -> Any:
    text = strip_thinking(reply)
    text = text.replace("```json", "```")
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError(f"no JSON object/array found in reply: {text[:200]!r}")
    start = min(starts)
    ends = [i for i in (text.rfind("}"), text.rfind("]")) if i != -1]
    end = max(ends)
    return json.loads(text[start : end + 1])
