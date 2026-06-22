from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AliasConfig:
    name: str
    model: str
    category: str


@dataclass(frozen=True)
class ChatTemplateConfig:
    enabled: bool = True
    enable_thinking: bool | None = None


@dataclass(frozen=True)
class GenerationConfig:
    max_new_tokens: int = 128
    do_sample: bool = False
    temperature: float = 0.0
    top_p: float = 1.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelConfig:
    name: str
    provider: str
    model_id: str
    task: str = "text-generation"
    dtype: str = "bfloat16"
    device_map: str = "auto"
    trust_remote_code: bool = True
    chat_template: ChatTemplateConfig = field(default_factory=ChatTemplateConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptConfig:
    name: str
    template: str
    objective: str = ""
    instructions: str = ""
    output_rules: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class ModelClient(Protocol):
    config: ModelConfig

    def generate(self, prompt: str) -> str:
        """Return the raw model response for a rendered prompt."""

    def generate_batch(self, prompts: list[str]) -> list[str]:
        """Return one raw model response for each rendered prompt."""
