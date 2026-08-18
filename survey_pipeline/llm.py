"""qwen3-32B para o resíduo LLM do survey_pipeline. Autocontido, reusa o
TransformersModelClient do repo, carrega uma vez (lru_cache). Requer PYTHONPATH=src.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from tqdm import tqdm

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
        chat_template=ChatTemplateConfig(enabled=True, enable_thinking=bool(g.get("enable_thinking", True))),
        generation=GenerationConfig(
            max_new_tokens=int(g.get("max_new_tokens", 2048)),
            do_sample=bool(g.get("do_sample", False)),
            temperature=float(g.get("temperature", 0.0)),
            top_p=float(g.get("top_p", 1.0)),
        ),
    )
    return TransformersModelClient(config)


def generate_batch(llm: ModelClient, prompts: list[str], *, chunk: int, desc: str = "Validando") -> list[str]:
    idx = [i for i, p in enumerate(prompts) if p and p.strip()]
    out = [""] * len(prompts)
    with tqdm(total=len(idx), desc=desc, unit="glosa") as bar:
        for start in range(0, len(idx), chunk):
            sub = idx[start : start + chunk]
            for i, r in zip(sub, llm.generate_batch([prompts[i] for i in sub])):
                out[i] = r
            bar.update(len(sub))
    return out
