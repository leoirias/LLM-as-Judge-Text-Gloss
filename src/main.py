from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from judge.runner import DatasetColumns, JudgeRunConfig, run_judge_dataset
from judge.summarize import summarize_results
from models.loader import load_model_client_from_alias, load_prompt_config


def main() -> None:
    args = _parse_args()
    experiment = _read_yaml(args.experiment)

    dataset_config = experiment["dataset"]
    runtime_config = experiment["runtime"]
    model_config = experiment["model"]
    prompt_config = experiment["prompt"]

    model = load_model_client_from_alias(model_config.get("alias", "judge"))
    prompt = load_prompt_config(prompt_config.get("name", "judge_v1"))

    run_config = JudgeRunConfig(
        dataset_path=Path(dataset_config["path"]),
        result_path=Path(runtime_config["result_path"]),
        columns=DatasetColumns(
            id=dataset_config.get("id_column", "id"),
            text=dataset_config.get("text_column", "text"),
            gloss=dataset_config.get("gloss_column", "gloss"),
        ),
        limit=runtime_config.get("limit"),
        resume=bool(runtime_config.get("resume", True)),
        save_every=int(runtime_config.get("save_every", 100)),
        batch_size=int(runtime_config.get("batch_size", 1)),
    )

    run_summary = run_judge_dataset(run_config, model=model, prompt_config=prompt)
    summary = summarize_results(
        results_path=Path(runtime_config["result_path"]),
        summary_path=Path(runtime_config["summary_path"]),
    )

    print({"run": run_summary, "summary": summary})


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an LLM-as-Judge experiment.")
    parser.add_argument(
        "--experiment",
        type=Path,
        required=True,
        help="Path to the experiment YAML config.",
    )
    return parser.parse_args()


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")

    return data


if __name__ == "__main__":
    main()
