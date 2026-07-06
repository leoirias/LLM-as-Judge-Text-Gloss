"""qwen3-32B access for the main pipeline (self-contained).

Builds its own ModelConfig from config.yaml (generation settings live here;
deterministic by default so iterative refinement converges) and reuses the
repo's TransformersModelClient. Loaded ONCE and shared so a single 32B copy
stays in GPU memory.
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
        chat_template=ChatTemplateConfig(enabled=True, enable_thinking=False),
        generation=GenerationConfig(
            max_new_tokens=int(g.get("max_new_tokens", 128)),
            do_sample=bool(g.get("do_sample", True)),
            temperature=float(g.get("temperature", 0.7)),
            top_p=float(g.get("top_p", 0.9)),
        ),
    )
    return TransformersModelClient(config)


def generate_batch(llm: ModelClient, prompts: list[str], *, chunk: int = 8) -> list[str]:
    """Batch in fixed-size chunks (the 32B + KV cache must fit one A100).
    Empty prompts are skipped."""
    idx = [i for i, p in enumerate(prompts) if p and p.strip()]
    out = [""] * len(prompts)
    for start in range(0, len(idx), chunk):
        sub = idx[start : start + chunk]
        replies = llm.generate_batch([prompts[i] for i in sub])
        for i, r in zip(sub, replies):
            out[i] = r
    return out
