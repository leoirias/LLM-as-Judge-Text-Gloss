from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from judge.schema import JudgeDecision, JudgeSchemaError


class JudgeParseError(ValueError):
    pass


def parse_judge_response(raw_response: str) -> JudgeDecision:
    data = _extract_json_object(raw_response)

    if not isinstance(data, dict):
        raise JudgeParseError("Model response JSON must be an object.")

    try:
        return JudgeDecision.from_dict(data)
    except JudgeSchemaError as exc:
        raise JudgeParseError(str(exc)) from exc


def _extract_json_object(raw_response: str) -> Any:
    decoder = json.JSONDecoder()
    text = raw_response.strip()

    if not text:
        raise JudgeParseError("Model response is empty.")

    for start_index, char in enumerate(text):
        if char != "{":
            continue

        try:
            value, _ = decoder.raw_decode(text[start_index:])
            return value
        except JSONDecodeError:
            continue

    raise JudgeParseError("No valid JSON object found in model response.")
