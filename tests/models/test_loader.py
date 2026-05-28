from models.loader import load_alias, load_model_config_from_alias, load_prompt_config


def test_load_alias() -> None:
    alias = load_alias("judge")

    assert alias.name == "judge"
    assert alias.model == "qwen3-8b"
    assert alias.category == "llm"


def test_load_model_config_from_alias() -> None:
    config = load_model_config_from_alias("judge")

    assert config.name == "qwen3-8b"
    assert config.provider == "transformers"
    assert config.model_id == "Qwen/Qwen3-8B"
    assert config.generation.max_new_tokens == 128


def test_load_prompt_config() -> None:
    prompt = load_prompt_config("judge_v1")

    assert prompt.name == "judge_v1"
    assert prompt.objective
    assert prompt.template
