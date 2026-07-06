"""Draw a reproducible random sample of (id, text, gloss) pairs.

    python -m make_sample --input data/processed/aslg_pc12.keep.csv \
        --output data/processed/sample_200.csv --n 200 --seed 42

Both normalization pipelines (B1 LLM-only, B2 hybrid) consume this exact
sample so their outputs are comparable row-for-row.
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=Path("data/processed/aslg_pc12.keep.csv"))
    p.add_argument("--output", type=Path, default=Path("data/processed/sample_200.csv"))
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    with args.input.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    rng = random.Random(args.seed)
    sample = rng.sample(rows, args.n)
    # keep original corpus order stable for readability
    sample.sort(key=lambda r: int(r["id"]))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "text", "gloss"])
        w.writeheader()
        w.writerows({"id": r["id"], "text": r["text"], "gloss": r["gloss"]} for r in sample)

    print(f"sampled {len(sample)} / {len(rows)} rows (seed={args.seed}) -> {args.output}")


if __name__ == "__main__":
    main()
