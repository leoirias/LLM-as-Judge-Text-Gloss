import pytest

from judge.parser import JudgeParseError, parse_judge_response


def test_parse_valid_json() -> None:
    decision = parse_judge_response('{"has_error": false}')

    assert decision.has_error is False
    assert decision.reason is None


def test_parse_json_with_surrounding_text() -> None:
    decision = parse_judge_response('Answer:\n{"has_error": true, "reason": "Missing object."}')

    assert decision.has_error is True
    assert decision.reason == "Missing object."


def test_parse_invalid_response_raises() -> None:
    with pytest.raises(JudgeParseError):
        parse_judge_response("not json")
