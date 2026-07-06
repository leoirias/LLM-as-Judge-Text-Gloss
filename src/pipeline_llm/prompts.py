"""Prompt builders for pipeline B1 (one prompt per stage, plain.md PART B1).

Each prompt receives the English `text` plus the gloss from the previous step
and returns the updated gloss. The model is told to output ONLY the gloss.
"""

from __future__ import annotations

from gloss_resources import (
    KNOWN_ERRORS,
    REORDER_RULES,
    TOKEN_RULES,
    fewshot_block,
)

_HEADER = (
    "You normalize an English sentence's ASL gloss to a fixed consultancy "
    "convention. You are given the English text (reference) and the current "
    "draft gloss. Apply ONLY the rules of THIS step. Do not apply other steps. "
    "Output ONLY the resulting gloss on a single line, uppercase, no quotes, "
    "no explanation."
)


def _wrap(rules_title: str, rules: str, text: str, gloss: str, extra: str = "") -> str:
    parts = [_HEADER, "", rules_title, rules]
    if extra:
        parts += ["", extra]
    parts += ["", f'English text: "{text}"', f"Current gloss: {gloss}", "Result gloss:"]
    return "\n".join(parts)


def prompt_errors(text: str, gloss: str) -> str:
    """Prompt 2 — fix known errors E2-E6."""
    return _wrap("Fix these known errors (and nothing else):", KNOWN_ERRORS, text, gloss)


def prompt_clean(text: str, gloss: str) -> str:
    """Prompt 3 — token-by-token cleaning R1-R9."""
    return _wrap("Apply these token rules (and nothing else):", TOKEN_RULES, text, gloss)


def prompt_reorder(text: str, gloss: str) -> str:
    """Prompt 4 — sentence reorganization R10-R15 (with gold few-shot)."""
    extra = "Convention examples:\n" + fewshot_block()
    return _wrap("Apply these sentence rules (and nothing else):", REORDER_RULES, text, gloss, extra)


def prompt_validate(text: str, gloss: str) -> str:
    """Prompt 5 — validate against the convention; reply CORRECT or a fixed gloss."""
    extra = "Convention examples:\n" + fewshot_block()
    rules = (
        "Check whether the gloss already follows the convention (errors E2-E6 "
        "and rules R1-R15). If it is correct, output it unchanged. If not, "
        "output the corrected gloss. Output ONLY the gloss."
    )
    return _wrap("Validate the gloss against the full convention:", rules, text, gloss, extra)
