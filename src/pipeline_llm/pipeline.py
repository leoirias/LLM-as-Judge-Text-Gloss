"""Pipeline B1 orchestration — LLM-only, stage by stage, batched.

Each stage runs over the WHOLE sample as one batch before moving on, so the
32B model processes 200 prompts per forward pass group instead of 1.
Stage 1 (language) is skipped: already handled in preprocessing.
"""

from __future__ import annotations

from gloss_llm import generate_batch
from gloss_resources import extract_gloss
from models.base import ModelClient
from pipeline_llm import prompts


def run_b1(
    samples: list[dict],
    llm: ModelClient,
    *,
    validate: bool = False,
    log=print,
) -> dict[str, str]:
    """Return {id -> gloss_output_1} for the given samples (id,text,gloss)."""
    ids = [r["id"] for r in samples]
    texts = [r["text"] for r in samples]
    gloss = [r["gloss"] for r in samples]

    stages = [
        ("P2 errors", prompts.prompt_errors),
        ("P3 clean", prompts.prompt_clean),
        ("P4 reorder", prompts.prompt_reorder),
    ]
    if validate:
        stages.append(("P5 validate", prompts.prompt_validate))

    for name, builder in stages:
        log(f"[B1] {name} ...")
        batch = [builder(t, g) for t, g in zip(texts, gloss)]
        replies = generate_batch(llm, batch)
        gloss = [extract_gloss(r) or prev for r, prev in zip(replies, gloss)]

    return dict(zip(ids, gloss))
