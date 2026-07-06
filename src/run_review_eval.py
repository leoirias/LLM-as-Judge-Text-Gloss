"""Review-set evaluation: feed (Input, Output) of pares_review.csv through both
pipelines and check whether they converge to Output review (the correct gloss,
= the gold convention).

Picks 5 pairs where Output != Output review and the Input was NOT used as
few-shot. Emits:

    text, output, output_review, gloss_output_llm, gloss_output_hybrid

    PYTHONPATH=src python -m run_review_eval \
        --review data/pares_review.csv \
        --output data/processed/review_compare.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from gloss_llm import get_llm
from gloss_resources import FEWSHOT
from pipeline_hybrid.pipeline import run_b2
from pipeline_llm.pipeline import run_b1


def _norm(s: str) -> str:
    return " ".join((s or "").split()).strip()


def _key(s: str) -> str:
    return _norm(s).lower().rstrip(" .?!")


# 5 chosen pairs (diff vs review, not few-shot), each exercising a distinct rule
CHOSEN = [
    "I need to check your blood test.",        # R5 drop subject I
    "Your blood test is ready now.",           # R10 time-front + R6 possessive
    "I need a laboratory test.",               # E5 abbreviation
    "I have high blood pressure.",             # E6 compound split
    "The doctor needs to examine your pneumonia.",  # R6 possessive (condition)
]


def select(review_path: Path) -> list[dict]:
    rows = list(csv.DictReader(review_path.open(encoding="utf-8")))
    fewshot = {_key(t) for t, _ in FEWSHOT}
    by_key = {}
    for r in rows:
        out, rev = _norm(r["Output"]), _norm(r["Output review"])
        if out != rev and _key(r["Input"]) not in fewshot:
            by_key[_key(r["Input"])] = r
    picked = []
    for i, want in enumerate(CHOSEN):
        r = by_key.get(_key(want))
        if r is None:
            raise SystemExit(f"chosen pair not found / not qualifying: {want!r}")
        picked.append({"id": str(i), "text": _norm(r["Input"]),
                       "gloss": _norm(r["Output"]), "review": _norm(r["Output review"])})
    return picked


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--review", type=Path, default=Path("data/pares_review.csv"))
    p.add_argument("--output", type=Path, default=Path("data/processed/review_compare.csv"))
    p.add_argument("--alias", default="qwen3-32b")
    args = p.parse_args()

    picked = select(args.review)
    print(f"selected {len(picked)} review pairs")

    llm = get_llm(args.alias)
    print("=== Pipeline B1 (LLM-only) ===")
    out1 = run_b1(picked, llm)
    print("=== Pipeline B2 (hybrid) ===")
    out2 = run_b2(picked, llm)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["text", "output", "output_review", "gloss_output_llm", "gloss_output_hybrid"])
        for r in picked:
            w.writerow([r["text"], r["gloss"], r["review"],
                        out1.get(r["id"], ""), out2.get(r["id"], "")])
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
