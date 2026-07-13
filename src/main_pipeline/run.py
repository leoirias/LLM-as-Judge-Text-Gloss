"""CLI for the main pipeline.

Input CSV is ragged on purpose (two use cases):
  - our own glosses (pares_review): 3 columns  text, gloss(draft), gloss_review
  - public datasets (aslg-pc12):    2 columns  text, gloss
Language filtering is preprocessing and is NOT done here.

ITERATIVE refinement: round r feeds the previous round's gloss back through the
pipeline (text + gloss_{r-1} -> gloss_r). A row early-stops as soon as its gloss
stops changing (gloss_r == gloss_{r-1}); the loop ends when all rows are stable
or at max_rounds. Output has one column per round actually run:

  text, gloss, gloss_review, gloss_llm_1, gloss_llm_2, ... gloss_llm_R

gloss_review is empty for aslg-pc12 rows. A converged row repeats its stable
value in later columns.

    PYTHONPATH=src python -m main_pipeline.run \
        --input data/app_consultoria/input.csv \
        --output data/app_consultoria/output.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import yaml

from main_pipeline.llm import get_llm
from main_pipeline.pipeline import run_judge, run_pipeline

CONFIG = Path(__file__).parent / "config.yaml"


def read_input(path: Path) -> list[dict]:
    """Read by column NAME (tolerates an id column / any column order).
    Needs a `text` column and a `gloss` column; `gloss_review` is optional."""
    rows: list[dict] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames or []
        for req in ("text", "gloss"):
            if req not in cols:
                raise SystemExit(f"{path.name}: missing column {req!r} (has {cols})")
        for r in reader:
            text = (r.get("text") or "").strip()
            if not text:
                continue
            rows.append({
                "text": text,
                "gloss": (r.get("gloss") or "").strip(),
                "review": (r.get("gloss_review") or r.get("review") or "").strip(),
            })
    return rows


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=Path(cfg["io"]["input"]))
    p.add_argument("--output", type=Path, default=Path(cfg["io"]["output"]))
    p.add_argument("--max-rounds", type=int, default=int(cfg.get("max_rounds", 5)))
    p.add_argument("--no-early-stop", action="store_true",
                   default=not bool(cfg.get("early_stop", True)))
    args = p.parse_args()

    samples = read_input(args.input)
    print(f"loaded {len(samples)} rows from {args.input}")

    llm = get_llm()
    stages = tuple(cfg.get("stages", ["errors", "clean", "reorder"]))
    bs = int(cfg.get("batch_size", 8))
    early_stop = not args.no_early_stop
    n = len(samples)

    cur = [s["gloss"] for s in samples]
    converged = [False] * n
    rounds_used = [args.max_rounds] * n    # per-row round at which it stabilized
    history: list[list[str]] = []          # history[r] = glosses after round r+1

    for r in range(args.max_rounds):
        active = [i for i in range(n) if not converged[i]]
        if not active:
            break
        print(f"=== round {r+1}/{args.max_rounds}  ({len(active)} active) ===")
        sub = [{"text": samples[i]["text"], "gloss": cur[i]} for i in active]
        out = run_pipeline(sub, llm, stages=stages, batch_size=bs)

        col = [""] * n                      # display column: blank if not run this round
        for k, i in enumerate(active):
            col[i] = out[k]
            if early_stop and out[k].strip() == cur[i].strip():
                converged[i] = True         # gloss_r == gloss_{r-1} -> stable
                rounds_used[i] = r + 1
            cur[i] = out[k]                 # working state for the next round
        history.append(col)

    rounds_run = len(history)
    print(f"rounds run: {rounds_run}; converged rows: {sum(converged)}/{n}")

    # final semantic judge on each row's final gloss (the working state `cur`)
    texts = [s["text"] for s in samples]
    judge = run_judge(texts, cur, llm, batch_size=bs)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["text", "gloss", "gloss_review", "rounds_used"]
                   + [f"gloss_llm_{i+1}" for i in range(rounds_run)]
                   + ["judge"])
        for j, s in enumerate(samples):
            w.writerow([s["text"], s["gloss"], s["review"], rounds_used[j]]
                       + [history[i][j] for i in range(rounds_run)]
                       + [judge[j]])
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
