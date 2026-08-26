"""Rule schema for extract_rules. Kept deliberately smaller than the SignGram
Blueprint taxonomy from the design doc: just enough fields to extract, cite,
and validate a rule against the gold pairs.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EvidenceChannel = Literal["string-checkable", "nonmanual", "spatial", "underspecified"]


class ExtractedRule(BaseModel):
    id: str
    feature: str
    trigger: str
    constraint: str
    exception: str | None = None
    evidence_channel: EvidenceChannel
    source_page: int
    source_quote: str
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractedRuleSet(BaseModel):
    rules: list[ExtractedRule]


class RuleMatch(BaseModel):
    pair_index: int
    complies: bool
    note: str = ""


class RuleMatchSet(BaseModel):
    matches: list[RuleMatch] = Field(default_factory=list)
