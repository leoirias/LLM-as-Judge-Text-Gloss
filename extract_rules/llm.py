"""qwen3-32B access for extract_rules — self-contained, own generation config.

Kept separate from src/main_pipeline/llm.py: that one runs deterministic,
thinking-off, short (128-token) generations tuned for emitting one gloss line.
Rule extraction and gold cross-checking are reasoning-heavy and need much
longer outputs, so this loads its own instance with thinking on and a much
higher max_new_tokens.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from models.base import ChatTemplateConfig, GenerationConfig, ModelClient, ModelConfig
from models.transformers import TransformersModelClient

_CFG = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def get_llm() -> ModelClient:
    m = _CFG["model"]
    g = _CFG.get("generation", {})
    config = ModelConfig(
        name=m.get("name", "qwen3-32b"),
        provider="transformers",
        model_id=m["model_id"],
        dtype=m.get("dtype", "bfloat16"),
        device_map=m.get("device_map", "cuda"),
        trust_remote_code=True,
        chat_template=ChatTemplateConfig(
            enabled=True,
            enable_thinking=bool(g.get("enable_thinking", True)),
        ),
        generation=GenerationConfig(
            max_new_tokens=int(g.get("max_new_tokens", 6000)),
            do_sample=bool(g.get("do_sample", False)),
            temperature=float(g.get("temperature", 0.0)),
            top_p=float(g.get("top_p", 1.0)),
        ),
    )
    return TransformersModelClient(config)
