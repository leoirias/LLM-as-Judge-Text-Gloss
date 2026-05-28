from __future__ import annotations

from typing import Any

from vllm import LLM, SamplingParams

from models.base import ModelConfig


class VLLMModelClient:
    """Model client backed by vLLM for high-throughput batched inference."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config
        engine_kwargs = _engine_kwargs(config)

        llm_kwargs: dict[str, Any] = {
            "model": config.model_id,
            "dtype": _resolve_dtype(config.dtype),
            "trust_remote_code": config.trust_remote_code,
            "tensor_parallel_size": int(engine_kwargs.get("tensor_parallel_size", 1)),
            "gpu_memory_utilization": float(engine_kwargs.get("gpu_memory_utilization", 0.9)),
            "enforce_eager": bool(engine_kwargs.get("enforce_eager", False)),
        }

        max_model_len = engine_kwargs.get("max_model_len")
        if max_model_len is not None:
            llm_kwargs["max_model_len"] = int(max_model_len)

        max_num_seqs = engine_kwargs.get("max_num_seqs")
        if max_num_seqs is not None:
            llm_kwargs["max_num_seqs"] = int(max_num_seqs)

        self.llm = LLM(**llm_kwargs)
        self.tokenizer = self.llm.get_tokenizer()

    def generate(self, prompt: str) -> str:
        return self.generate_batch([prompt])[0]

    def generate_batch(self, prompts: list[str]) -> list[str]:
        if not prompts:
            return []

        rendered_prompts = [self._render_prompt(prompt) for prompt in prompts]
        sampling = SamplingParams(**self._sampling_kwargs())
        outputs = self.llm.generate(rendered_prompts, sampling, use_tqdm=False)
        return [output.outputs[0].text.strip() for output in outputs]

    def _render_prompt(self, prompt: str) -> str:
        if not self.config.chat_template.enabled:
            return prompt

        messages = [{"role": "user", "content": prompt}]
        kwargs: dict[str, Any] = {
            "tokenize": False,
            "add_generation_prompt": True,
        }

        if self.config.chat_template.enable_thinking is not None:
            kwargs["enable_thinking"] = self.config.chat_template.enable_thinking

        try:
            return self.tokenizer.apply_chat_template(messages, **kwargs)
        except TypeError:
            kwargs.pop("enable_thinking", None)
            return self.tokenizer.apply_chat_template(messages, **kwargs)

    def _sampling_kwargs(self) -> dict[str, Any]:
        generation = self.config.generation
        kwargs: dict[str, Any] = {
            "max_tokens": generation.max_new_tokens,
        }

        if generation.do_sample:
            kwargs["temperature"] = generation.temperature
            kwargs["top_p"] = generation.top_p
        else:
            kwargs["temperature"] = 0.0

        kwargs.update(generation.extra)
        return kwargs


def _engine_kwargs(config: ModelConfig) -> dict[str, Any]:
    value = config.extra.get("vllm", {}) if isinstance(config.extra, dict) else {}
    return value if isinstance(value, dict) else {}


def _resolve_dtype(dtype: str) -> str:
    normalized = dtype.lower()
    if normalized == "auto":
        return "auto"
    if normalized in {"float32", "fp32"}:
        return "float32"
    if normalized in {"bfloat16", "bf16"}:
        return "bfloat16"
    if normalized in {"float16", "fp16", "half"}:
        return "float16"

    raise ValueError(f"Unsupported vllm dtype: {dtype!r}")
