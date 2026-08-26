import json
from pathlib import Path

from judge.summarize import build_summary


def test_build_summary_from_json_result_file(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            [
                {"id": "1", "has_error": False, "parse_error": False},
                {"id": "2", "has_error": True, "parse_error": False},
                {"id": "3", "has_error": None, "parse_error": True},
            ]
        ),
        encoding="utf-8",
    )

    assert build_summary(result_path) == {
        "total": 3,
        "errors_detected": 1,
        "error_rate": 1 / 3,
        "parse_failed": 1,
        "parse_failure_rate": 1 / 3,
    }
