from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from judge.schema import JudgeDecision, JudgeSchemaError

_C_TO_LABEL = {1: "wrong", 2: "partial", 3: "correct"}


class JudgeParseError(ValueError):
    pass


def parse_judge_response(raw_response: str) -> JudgeDecision:
    data = _extract_json_object(raw_response)

    if not isinstance(data, dict):
        raise JudgeParseError("Model response JSON must be an object.")

    c = data.get("c")
    if c not in _C_TO_LABEL:
        raise JudgeParseError(
            f"Invalid value for 'c': {c!r}. Expected 1 (wrong), 2 (partial), or 3 (correct)."
        )

    classification = _C_TO_LABEL[c]
    reason = None
    if classification != "correct":
        reason = data.get("r") or None
        if reason:
            reason = str(reason).strip() or None

    try:
        return JudgeDecision(classification=classification, reason=reason)
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
