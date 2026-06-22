from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from models.base import (
    AliasConfig,
    ChatTemplateConfig,
    GenerationConfig,
    ModelClient,
    ModelConfig,
    PromptConfig,
)


MODELS_DIR = Path(__file__).resolve().parent
CONFIGS_DIR = MODELS_DIR / "configs"
PROMPTS_DIR = MODELS_DIR / "prompts"


def load_alias(alias_name: str, config_dir: Path | str = CONFIGS_DIR) -> AliasConfig:
    data = _read_yaml(Path(config_dir) / "aliases.yaml")
    aliases = _get_mapping(data, "aliases", source="aliases.yaml")

    if alias_name not in aliases:
        raise KeyError(_missing_key_message("alias", alias_name, aliases))

    alias_data = _ensure_mapping(aliases[alias_name], context=f"alias {alias_name!r}")
    return AliasConfig(
        name=alias_name,
        model=_required_str(alias_data, "model", context=f"alias {alias_name!r}"),
        category=str(alias_data.get("category", "llm")),
    )


def load_model_config(
    model_name: str,
    config_dir: Path | str = CONFIGS_DIR,
) -> ModelConfig:
    data = _read_yaml(Path(config_dir) / "models.yaml")
    models = _get_mapping(data, "models", source="models.yaml")

    if model_name not in models:
        raise KeyError(_missing_key_message("model", model_name, models))

    model_data = _ensure_mapping(models[model_name], context=f"model {model_name!r}")
    generation_data = _ensure_mapping(
        model_data.get("generation", {}),
        context=f"model {model_name!r}.generation",
    )
    chat_template_data = _ensure_mapping(
        model_data.get("chat_template", {}),
        context=f"model {model_name!r}.chat_template",
    )

    generation_known_keys = {"max_new_tokens", "do_sample", "temperature", "top_p"}
    model_known_keys = {
        "provider",
        "model_id",
        "task",
        "dtype",
        "device_map",
        "trust_remote_code",
        "chat_template",
        "generation",
    }

    return ModelConfig(
        name=model_name,
        provider=_required_str(model_data, "provider", context=f"model {model_name!r}"),
        model_id=_required_str(model_data, "model_id", context=f"model {model_name!r}"),
        task=str(model_data.get("task", "text-generation")),
        dtype=str(model_data.get("dtype", "bfloat16")),
        device_map=str(model_data.get("device_map", "auto")),
        trust_remote_code=bool(model_data.get("trust_remote_code", True)),
        chat_template=ChatTemplateConfig(
            enabled=bool(chat_template_data.get("enabled", True)),
            enable_thinking=chat_template_data.get("enable_thinking"),
        ),
        generation=GenerationConfig(
            max_new_tokens=int(generation_data.get("max_new_tokens", 128)),
            do_sample=bool(generation_data.get("do_sample", False)),
            temperature=float(generation_data.get("temperature", 0.0)),
            top_p=float(generation_data.get("top_p", 1.0)),
            extra=_unknown_keys(generation_data, generation_known_keys),
        ),
        extra=_unknown_keys(model_data, model_known_keys),
    )


def load_model_config_from_alias(
    alias_name: str,
    config_dir: Path | str = CONFIGS_DIR,
) -> ModelConfig:
    alias = load_alias(alias_name, config_dir=config_dir)
    return load_model_config(alias.model, config_dir=config_dir)


def load_model_client_from_alias(
    alias_name: str,
    config_dir: Path | str = CONFIGS_DIR,
) -> ModelClient:
    config = load_model_config_from_alias(alias_name, config_dir=config_dir)

    if config.provider == "transformers":
        from models.transformers import TransformersModelClient

        return TransformersModelClient(config)

    if config.provider == "vllm":
        from models.vllm_client import VLLMModelClient

        return VLLMModelClient(config)

    if config.provider == "openai":
        from models.openai_client import OpenAIModelClient

        return OpenAIModelClient(config)

    raise ValueError(f"Unsupported model provider: {config.provider!r}")


def load_prompt_config(
    prompt_name: str,
    prompts_dir: Path | str = PROMPTS_DIR,
) -> PromptConfig:
    prompt_path = Path(prompts_dir) / f"{prompt_name}.yaml"

    if not prompt_path.exists():
        available = sorted(p.stem for p in Path(prompts_dir).glob("*.yaml"))
        available_str = ", ".join(available) or "<none>"
        raise KeyError(
            f"Unknown prompt {prompt_name!r}. Available prompts: {available_str}"
        )

    prompt_data = _read_yaml(prompt_path)
    known_keys = {"objective", "instructions", "output_rules", "template"}

    return PromptConfig(
        name=prompt_name,
        template=_required_str(prompt_data, "template", context=f"prompt {prompt_name!r}"),
        objective=str(prompt_data.get("objective", "") or ""),
        instructions=str(prompt_data.get("instructions", "") or ""),
        output_rules=str(prompt_data.get("output_rules", "") or ""),
        extra=_unknown_keys(prompt_data, known_keys),
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    return _ensure_mapping(data, context=str(path))


def _get_mapping(data: dict[str, Any], key: str, source: str) -> dict[str, Any]:
    if key not in data:
        raise KeyError(f"Missing top-level key {key!r} in {source}")

    return _ensure_mapping(data[key], context=f"{source}.{key}")


def _ensure_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"Expected a mapping for {context}, got {type(value).__name__}")

    return value


def _required_str(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)

    if value is None or str(value).strip() == "":
        raise KeyError(f"Missing required key {key!r} in {context}")

    return str(value)


def _unknown_keys(data: dict[str, Any], known_keys: set[str]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key not in known_keys}


def _missing_key_message(kind: str, name: str, values: dict[str, Any]) -> str:
    available = ", ".join(sorted(values)) or "<none>"
    return f"Unknown {kind} {name!r}. Available {kind}s: {available}"
