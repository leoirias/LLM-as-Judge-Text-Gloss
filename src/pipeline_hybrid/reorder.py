"""Stage 4 (B2) — sentence reorganization R10-R15 via the LLM, one pass.

These rules interact (time-fronting + WH position + tense marker happen in the
same sentence), so a single LLM call per row handles them together. The gloss
arriving here is already token-clean (Stage 3), so the model only reorders /
marks, it does not re-clean.
"""

from __future__ import annotations

from gloss_llm import generate_batch
from gloss_resources import REORDER_RULES, extract_gloss, fewshot_block
from models.base import ModelClient

_HEADER = (
    "You reorganize an already-cleaned ASL gloss into the consultancy "
    "convention. The gloss is already uppercase and free of articles, copulas, "
    "auxiliaries and dropped pronouns. Apply ONLY the sentence rules below. "
    "Output ONLY the resulting gloss on a single line, no explanation."
)


def build_prompt(text: str, gloss: str) -> str:
    return "\n".join([
        _HEADER, "",
        "Sentence rules:", REORDER_RULES, "",
        "Convention examples:", fewshot_block(), "",
        f'English text: "{text}"',
        f"Cleaned gloss: {gloss}",
        "Result gloss:",
    ])


def reorder_batch(llm: ModelClient, texts: list[str], glosses: list[str]) -> list[str]:
    prompts = [build_prompt(t, g) for t, g in zip(texts, glosses)]
    replies = generate_batch(llm, prompts)
    return [extract_gloss(r) or prev for r, prev in zip(replies, glosses)]
