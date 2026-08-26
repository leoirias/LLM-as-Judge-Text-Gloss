from judge.prompt import build_judge_prompt
from models.loader import load_prompt_config


def test_build_judge_prompt_renders_fragments_and_variables() -> None:
    prompt_config = load_prompt_config("judge_v1")
    prompt = build_judge_prompt(
        prompt_config,
        text="What is your name?",
        gloss="NAME YOU WHAT(wh)",
    )

    assert "@{" not in prompt
    assert "{{" not in prompt
    assert "What is your name?" in prompt
    assert "NAME YOU WHAT(wh)" in prompt
    assert '{"has_error": false}' in prompt
