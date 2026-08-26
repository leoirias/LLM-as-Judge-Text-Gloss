import csv
from pathlib import Path

from judge.runner import JudgeRunConfig, run_judge_dataset
from models.base import ModelConfig, PromptConfig


class FakeModel:
    config = ModelConfig(name="fake", provider="test", model_id="fake-model")

    def generate(self, prompt: str) -> str:
        return '{"has_error": false}'

    def generate_batch(self, prompts: list[str]) -> list[str]:
        return ['{"has_error": false}' for _ in prompts]


def test_run_judge_dataset_writes_json_result_file(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.csv"
    result_path = tmp_path / "result.json"
    prompt_config = PromptConfig(
        name="test_prompt",
        objective="Judge the gloss.",
        instructions="Return JSON.",
        output_rules='Use {"has_error": false}.',
        template="@{objective}\n{{ text }}\n{{ gloss }}",
    )

    with dataset_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["id", "text", "gloss"])
        writer.writeheader()
        writer.writerow({"id": "1", "text": "What is your name?", "gloss": "NAME YOU WHAT(wh)"})

    summary = run_judge_dataset(
        JudgeRunConfig(
            dataset_path=dataset_path,
            result_path=result_path,
            save_every=1,
            batch_size=2,
        ),
        model=FakeModel(),
        prompt_config=prompt_config,
    )

    assert summary == {
        "processed": 1,
        "skipped": 0,
        "errors_detected": 0,
        "parse_failed": 0,
    }
    assert result_path.read_text(encoding="utf-8").startswith("[")
