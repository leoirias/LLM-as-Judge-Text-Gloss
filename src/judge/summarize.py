from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def summarize_results(results_path: Path, summary_path: Path) -> dict[str, Any]:
    summary = build_summary(results_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    with summary_path.open("w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)
        file.write("\n")

    return summary


def build_summary(results_path: Path) -> dict[str, Any]:
    with results_path.open("r", encoding="utf-8") as file:
        records = json.load(file)

    if not isinstance(records, list):
        raise ValueError(f"Expected a JSON list in {results_path}")

    total = len(records)
    parse_failed = sum(1 for r in records if r.get("parse_error") is True)

    by_classification: dict[str, int] = {}
    for r in records:
        if r.get("parse_error"):
            continue
        cls = r.get("classification")
        if cls:
            by_classification[cls] = by_classification.get(cls, 0) + 1

    errors_detected = by_classification.get("wrong", 0)

    return {
        "total": total,
        "errors_detected": errors_detected,
        "error_rate": errors_detected / total if total else 0.0,
        "parse_failed": parse_failed,
        "parse_failure_rate": parse_failed / total if total else 0.0,
        "by_classification": by_classification,
    }
