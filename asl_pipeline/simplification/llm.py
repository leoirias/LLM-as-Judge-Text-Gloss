"""Client do modelo de extração — autocontido, config própria (config.yaml).

Qwen3-30B-A3B-Instruct-2507: MoE (30,5B totais / 3,3B ativos), variante
non-thinking (não é "thinking desligado numa gramática híbrida", é um
checkpoint treinado direto pra resposta sem raciocínio) — extração é uma
tarefa de leitura+preenchimento de campos, não de dedução em várias etapas,
e thinking já mostrou risco de travar sem fechar o JSON no juiz de Libras
deste mesmo projeto (ver survey_pipeline/config_libras.yaml). Cabe com folga
numa A100 80GB (pesos ~61GB), sobrando VRAM pra KV-cache das janelas longas.

Requer PYTHONPATH=src.
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
        name=m.get("name", "qwen3-30b-a3b-instruct-2507"),
        provider="transformers",
        model_id=m["model_id"],
        dtype=m.get("dtype", "bfloat16"),
        device_map=m.get("device_map", "cuda"),
        trust_remote_code=True,
        chat_template=ChatTemplateConfig(
            enabled=True,
            enable_thinking=g.get("enable_thinking"),
        ),
        generation=GenerationConfig(
            max_new_tokens=int(g.get("max_new_tokens", 4000)),
            do_sample=bool(g.get("do_sample", False)),
            temperature=float(g.get("temperature", 0.0)),
            top_p=float(g.get("top_p", 1.0)),
        ),
    )
    return TransformersModelClient(config)
