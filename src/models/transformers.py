from __future__ import annotations

from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from models.base import ModelConfig


class TransformersModelClient:
    """Model client backed by Hugging Face Transformers causal LMs."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config
        self.tokenizer = AutoTokenizer.from_pretrained(
            config.model_id,
            trust_remote_code=config.trust_remote_code,
        )

        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.tokenizer.padding_side = "left"

        self.model = AutoModelForCausalLM.from_pretrained(
            config.model_id,
            dtype=_resolve_dtype(config.dtype),
            device_map=config.device_map,
            trust_remote_code=config.trust_remote_code,
            attn_implementation="sdpa",
        )
        self.model.eval()

    @torch.inference_mode()
    def generate(self, prompt: str) -> str:
        return self.generate_batch([prompt])[0]

    @torch.inference_mode()
    def generate_batch(self, prompts: list[str]) -> list[str]:
        if not prompts:
            return []

        rendered_prompts = [self._render_prompt(prompt) for prompt in prompts]
        inputs = self.tokenizer(
            rendered_prompts,
            return_tensors="pt",
            padding=True,
            truncation=False,
        )
        inputs = {key: value.to(self._input_device()) for key, value in inputs.items()}

        output_ids = self.model.generate(
            **inputs,
            pad_token_id=self.tokenizer.pad_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
            **self._generation_kwargs(),
        )

        prompt_length = inputs["input_ids"].shape[-1]
        responses = []

        for sequence in output_ids:
            generated_ids = sequence[prompt_length:]
            responses.append(self.tokenizer.decode(generated_ids, skip_special_tokens=True).strip())

        return responses

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

    def _generation_kwargs(self) -> dict[str, Any]:
        generation = self.config.generation
        kwargs: dict[str, Any] = {
            "max_new_tokens": generation.max_new_tokens,
            "do_sample": generation.do_sample,
        }

        if generation.do_sample:
            kwargs["temperature"] = generation.temperature
            kwargs["top_p"] = generation.top_p

        kwargs.update(generation.extra)
        return kwargs

    def _input_device(self) -> torch.device:
        try:
            return self.model.device
        except AttributeError:
            return next(self.model.parameters()).device


def _resolve_dtype(dtype: str) -> torch.dtype | str:
    normalized = dtype.lower()
    if normalized == "auto":
        return "auto"
    if normalized in {"float32", "fp32"}:
        return torch.float32
    if normalized in {"bfloat16", "bf16"}:
        return torch.bfloat16
    if normalized in {"float16", "fp16", "half"}:
        return torch.float16

    raise ValueError(f"Unsupported torch dtype: {dtype!r}")
