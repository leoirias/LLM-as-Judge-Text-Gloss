from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from tqdm import tqdm

from judge.parser import JudgeParseError, parse_judge_response
from judge.prompt import build_judge_prompt
from models.base import ModelClient, PromptConfig


@dataclass(frozen=True)
class DatasetColumns:
    id: str = "id"
    text: str = "text"
    gloss: str = "gloss"


@dataclass(frozen=True)
class JudgeRunConfig:
    dataset_path: Path
    result_path: Path
    columns: DatasetColumns = DatasetColumns()
    limit: int | None = None
    resume: bool = True
    save_every: int = 100
    batch_size: int = 1


def run_judge_dataset(
    config: JudgeRunConfig,
    model: ModelClient,
    prompt_config: PromptConfig,
) -> dict[str, int]:
    config.result_path.parent.mkdir(parents=True, exist_ok=True)
    records = _load_result_records(config.result_path) if config.resume else []
    completed_ids = {str(record["id"]) for record in records if "id" in record}

    processed = 0
    skipped = 0
    parse_failed = 0
    errors_detected = 0
    processed_since_save = 0

    pending_batch: list[dict[str, str]] = []
    rows = _iter_dataset_rows(config)

    for row in tqdm(rows, desc="Judging gloss pairs"):
        row_id = row[config.columns.id]

        if row_id in completed_ids:
            skipped += 1
            continue

        pending_batch.append(row)

        if len(pending_batch) >= config.batch_size:
            batch_summary = _process_batch(
                batch=pending_batch,
                config=config,
                model=model,
                prompt_config=prompt_config,
                records=records,
                completed_ids=completed_ids,
            )
            processed += batch_summary["processed"]
            processed_since_save += batch_summary["processed"]
            errors_detected += batch_summary["errors_detected"]
            parse_failed += batch_summary["parse_failed"]
            pending_batch = []

            if config.save_every > 0 and processed_since_save >= config.save_every:
                _write_result_records(config.result_path, records)
                processed_since_save = 0

    if pending_batch:
        batch_summary = _process_batch(
            batch=pending_batch,
            config=config,
            model=model,
            prompt_config=prompt_config,
            records=records,
            completed_ids=completed_ids,
        )
        processed += batch_summary["processed"]
        processed_since_save += batch_summary["processed"]
        errors_detected += batch_summary["errors_detected"]
        parse_failed += batch_summary["parse_failed"]

    _write_result_records(config.result_path, records)

    return {
        "processed": processed,
        "skipped": skipped,
        "errors_detected": errors_detected,
        "parse_failed": parse_failed,
    }


def _process_batch(
    batch: list[dict[str, str]],
    config: JudgeRunConfig,
    model: ModelClient,
    prompt_config: PromptConfig,
    records: list[dict[str, Any]],
    completed_ids: set[str],
) -> dict[str, int]:
    prompts = [
        build_judge_prompt(
            prompt_config,
            text=row[config.columns.text],
            gloss=row[config.columns.gloss],
        )
        for row in batch
    ]
    raw_responses = model.generate_batch(prompts)

    if len(raw_responses) != len(batch):
        raise RuntimeError(
            f"Model returned {len(raw_responses)} responses for {len(batch)} prompts."
        )

    processed = 0
    parse_failed = 0
    errors_detected = 0

    for row, raw_response in zip(batch, raw_responses, strict=True):
        record = _build_result_record(
            row=row,
            config=config,
            raw_response=raw_response,
            model_name=model.config.name,
            prompt_name=prompt_config.name,
        )

        if record["has_error"] is True:
            errors_detected += 1
        if record["parse_error"]:
            parse_failed += 1

        records.append(record)
        completed_ids.add(row[config.columns.id])
        processed += 1

    return {
        "processed": processed,
        "errors_detected": errors_detected,
        "parse_failed": parse_failed,
    }


def _iter_dataset_rows(config: JudgeRunConfig) -> Iterable[dict[str, str]]:
    with config.dataset_path.open("r", encoding="utf-8", newline="") as dataset_file:
        reader = csv.DictReader(dataset_file)
        _validate_columns(reader.fieldnames or [], config.columns)

        for index, row in enumerate(reader):
            if config.limit is not None and index >= config.limit:
                break

            yield row


def _validate_columns(fieldnames: list[str], columns: DatasetColumns) -> None:
    required = {columns.id, columns.text, columns.gloss}
    missing = required - set(fieldnames)

    if missing:
        raise ValueError(f"Dataset is missing required columns: {sorted(missing)}")


def _build_result_record(
    row: dict[str, str],
    config: JudgeRunConfig,
    raw_response: str,
    model_name: str,
    prompt_name: str,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": row[config.columns.id],
        "text": row[config.columns.text],
        "gloss": row[config.columns.gloss],
        "model": model_name,
        "prompt": prompt_name,
        "has_error": None,
        "classification": None,
        "reason": None,
        "parse_error": False,
        "error_message": None,
        "raw_response": raw_response,
    }

    try:
        decision = parse_judge_response(raw_response)
    except JudgeParseError as exc:
        record["parse_error"] = True
        record["error_message"] = str(exc)
        return record

    record.update(decision.to_dict())
    return record


def _load_result_records(result_path: Path) -> list[dict[str, Any]]:
    if not result_path.exists():
        return []

    content = result_path.read_text(encoding="utf-8").strip()
    if not content:
        return []

    data = json.loads(content)

    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {result_path}")

    return data


def _write_result_records(result_path: Path, records: list[dict[str, Any]]) -> None:
    temp_path = result_path.with_suffix(result_path.suffix + ".tmp")

    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)
        file.write("\n")

    temp_path.replace(result_path)
