"""Run both normalization pipelines over the same sample and emit the artifact.

Loads qwen3-32B ONCE (shared by B1 and B2), runs B1 (LLM-only) then B2
(hybrid), and writes:

    id, text, gloss_input, gloss_output_1, gloss_output_2

    PYTHONPATH=src HF_HOME=/workspace/.cache/huggingface \
      python -m run_pipelines \
        --sample data/processed/sample_200.csv \
        --output data/processed/normalization_compare.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from gloss_llm import get_llm
from pipeline_hybrid.pipeline import run_b2
from pipeline_llm.pipeline import run_b1


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=Path, default=Path("data/processed/sample_200.csv"))
    p.add_argument("--output", type=Path, default=Path("data/processed/normalization_compare.csv"))
    p.add_argument("--alias", default="qwen3-32b")
    p.add_argument("--validate", action="store_true", help="run B1 Prompt 5 (validation) too")
    args = p.parse_args()

    with args.sample.open(newline="", encoding="utf-8") as fh:
        samples = list(csv.DictReader(fh))
    print(f"loaded {len(samples)} pairs from {args.sample}")

    llm = get_llm(args.alias)

    print("=== Pipeline B1 (LLM-only) ===")
    out1 = run_b1(samples, llm, validate=args.validate)
    print("=== Pipeline B2 (hybrid) ===")
    out2 = run_b2(samples, llm)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "text", "gloss_input", "gloss_output_1", "gloss_output_2"])
        for r in samples:
            i = r["id"]
            w.writerow([i, r["text"], r["gloss"], out1.get(i, ""), out2.get(i, "")])
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
