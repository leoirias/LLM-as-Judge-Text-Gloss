"""Pipeline B2 orchestration — hybrid (functions + LLM).

Deterministic stages (mojibake, clean) run for every row on CPU, then the LLM
reorder stage runs once as a single batch. Stage 1 (language) is skipped:
already handled in preprocessing.
"""

from __future__ import annotations

from models.base import ModelClient
from pipeline_hybrid import clean, mojibake, reorder, validate


def run_b2(samples: list[dict], llm: ModelClient, *, log=print) -> dict[str, str]:
    """Return {id -> gloss_output_2} for the given samples (id,text,gloss)."""
    ids = [r["id"] for r in samples]
    texts = [r["text"] for r in samples]
    gloss_in = [r["gloss"] for r in samples]

    log("[B2] stage2 mojibake (ftfy + align) ...")
    fixed, moji_ok = [], []
    for t, g in zip(texts, gloss_in):
        fg, ok = mojibake.fix(t, g)
        fixed.append(fg)
        moji_ok.append(ok)

    log("[B2] stage3 clean (functions + spaCy) ...")
    cleaned = [clean.clean(t, g) for t, g in zip(texts, fixed)]

    log("[B2] stage4 reorder (LLM, batched) ...")
    reordered = reorder.reorder_batch(llm, texts, cleaned)

    # validator (status is informational; not part of the 5-column artifact)
    for t, gi, go, ok in zip(texts, gloss_in, reordered, moji_ok):
        validate.status(t, gi, go, ok)

    return dict(zip(ids, reordered))
