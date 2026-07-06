"""Orchestrates the LLM-only pipeline: P1 errors -> P2 clean -> P3 reorder.

Each stage is one batched LLM call over all rows; the gloss is carried forward.
Returns the final gloss for each sample. Multiple "rounds" (re-runs) are driven
by the caller (run.py) — with sampling on, each round can differ.
"""

from __future__ import annotations

from pathlib import Path

from main_pipeline import resources
from main_pipeline.llm import generate_batch
from main_pipeline.prompt_loader import load, render
from models.base import ModelClient

PROMPTS_DIR = Path(__file__).parent / "prompts"
STAGE_FILE = {
    "errors": "01_errors.yaml",
    "clean": "02_clean.yaml",
    "reorder": "03_reorder.yaml",
}
JUDGE_FILE = "04_judge.yaml"


def _verdict(reply: str) -> str:
    lines = [ln.strip() for ln in (reply or "").splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def run_judge(texts: list[str], glosses: list[str], llm, *, batch_size: int = 8,
              log=print) -> list[str]:
    """Final semantic layer: does the gloss still express the original meaning?
    Returns one verdict per row ('OK' or 'MISSING: <word> - <reason>')."""
    log("[main_pipeline] judge (semantic adequacy) ...")
    data = load(str(PROMPTS_DIR / JUDGE_FILE))
    prompts = [render(data, {"text": t, "gloss": g}) for t, g in zip(texts, glosses)]
    replies = generate_batch(llm, prompts, chunk=batch_size)
    return [_verdict(r) for r in replies]


def _run_stage(stage, texts, glosses, llm, batch_size, fewshot):
    data = load(str(PROMPTS_DIR / STAGE_FILE[stage]))
    prompts = [render(data, {"text": t, "gloss": g, "few_shot": fewshot})
               for t, g in zip(texts, glosses)]
    replies = generate_batch(llm, prompts, chunk=batch_size)
    return [resources.extract_gloss(r) or prev for r, prev in zip(replies, glosses)]


def run_pipeline(
    samples: list[dict],
    llm: ModelClient,
    *,
    stages=("errors", "clean", "reorder"),
    batch_size: int = 8,
    log=print,
) -> list[str]:
    texts = [s["text"] for s in samples]
    glosses = [s["gloss"] for s in samples]
    # few-shot must never contain a test sentence: exclude all input texts
    fewshot = resources.fewshot_block(exclude=set(texts))
    for i, stage in enumerate(stages):
        log(f"[main_pipeline] P{i+1} {stage} ...")
        glosses = _run_stage(stage, texts, glosses, llm, batch_size, fewshot)
    return glosses
