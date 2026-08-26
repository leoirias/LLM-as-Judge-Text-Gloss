import pytest

from judge.schema import JudgeDecision, JudgeSchemaError


def test_valid_correct_decision_has_no_reason() -> None:
    decision = JudgeDecision.from_dict({"has_error": False})

    assert decision.to_dict() == {"has_error": False}


def test_error_decision_requires_reason() -> None:
    with pytest.raises(JudgeSchemaError):
        JudgeDecision.from_dict({"has_error": True})


def test_error_decision_keeps_reason() -> None:
    decision = JudgeDecision.from_dict({"has_error": True, "reason": "Meaning changed."})

    assert decision.to_dict() == {"has_error": True, "reason": "Meaning changed."}
