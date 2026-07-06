"""Validator + confidence (B2) — deterministic checks, not a mutator.

Confirms the verifiable parts (time-marker fronting R10, punctuation R15) and
derives a status. It does not change the gloss; low confidence -> human.
(Self-consistency over N Stage-4 runs is a future extension; see plain.md.)
"""

from __future__ import annotations

TIME_WORDS = {"NOW", "TODAY", "TOMORROW", "THIS_MORNING", "YESTERDAY"}


def status(text: str, gloss_in: str, gloss_out: str, mojibake_ok: bool) -> str:
    """ok | corrigida | humano."""
    if not mojibake_ok or not gloss_out.strip():
        return "humano"
    toks = gloss_out.split()
    # R10: if a time word is present it should be at the front
    time_pos = [i for i, t in enumerate(toks) if t in TIME_WORDS]
    if time_pos and min(time_pos) != 0:
        return "humano"
    # R15: question mark iff the source text is a question
    q_src = text.strip().endswith("?")
    q_out = gloss_out.strip().endswith("?")
    if q_src != q_out:
        return "humano"
    return "ok" if gloss_out.strip() == gloss_in.strip() else "corrigida"
