from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from openai import OpenAI

from models.base import ModelConfig


class OpenAIModelClient:
    # Conservative ceiling to stay under typical Tier 1 RPM limits while still
    # parallelising calls within a runner batch.
    _MAX_CONCURRENT = 5

    def __init__(self, config: ModelConfig) -> None:
        self.config = config
        self._client = OpenAI()  # reads OPENAI_API_KEY from the environment

    def generate(self, prompt: str) -> str:
        return self._call(prompt)

    def generate_batch(self, prompts: list[str]) -> list[str]:
        if not prompts:
            return []

        workers = min(len(prompts), self._MAX_CONCURRENT)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(self._call, prompts))

    def _call(self, prompt: str) -> str:
        generation = self.config.generation
        kwargs: dict[str, Any] = {
            "model": self.config.model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_completion_tokens": generation.max_new_tokens,
        }

        if generation.do_sample:
            kwargs["temperature"] = generation.temperature
            kwargs["top_p"] = generation.top_p
        else:
            kwargs["temperature"] = 0.0

        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""
