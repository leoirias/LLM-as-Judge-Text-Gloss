"""Thin shared access to the qwen3-32B client used by both pipelines.

Reuses the repo's model-loading plumbing (cluster-tuned: cu121 torch, offline
HF, transformers provider). Loaded ONCE and shared so we never hold two copies
of a 32B model in GPU memory.
"""

from __future__ import annotations

from functools import lru_cache

from models.base import ModelClient
from models.loader import load_model_client_from_alias

ALIAS = "qwen3-32b"


@lru_cache(maxsize=1)
def get_llm(alias: str = ALIAS) -> ModelClient:
    return load_model_client_from_alias(alias)


def generate_batch(llm: ModelClient, prompts: list[str], *, chunk: int = 8) -> list[str]:
    """Batch call in fixed-size chunks (the 32B + KV cache must fit one A100;
    feeding all 200 long prompts at once would OOM). Empty prompts are skipped.
    """
    idx = [i for i, p in enumerate(prompts) if p and p.strip()]
    out = [""] * len(prompts)
    for start in range(0, len(idx), chunk):
        sub = idx[start : start + chunk]
        replies = llm.generate_batch([prompts[i] for i in sub])
        for i, r in zip(sub, replies):
            out[i] = r
    return out
