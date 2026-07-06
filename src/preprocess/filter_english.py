"""Stage 1 CLI — drop non-English pairs from a (id, text, gloss) CSV.

Policy (binary): keep the pair iff fastText's top-1 language for the
``text`` column is English; otherwise discard it.

Outputs into --outdir:
  <stem>.keep.csv          id,text,gloss          -> the base going forward
  <stem>.discarded_ids.csv id                     -> for quick verification
  <stem>.discard.csv       id,text,gloss,pred_lang,pred_prob  -> audit detail

    python -m preprocess.filter_english \
        --input data/ASLG-PC12/aslg_pc12.csv \
        --outdir data/processed
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from preprocess.language_id import LanguageIdentifier


def run(
    input_path: Path,
    outdir: Path,
    *,
    text_col: str,
    id_col: str,
    min_prob: float,
    batch_size: int,
) -> dict[str, int]:
    with input_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        for col in (text_col, id_col):
            if col not in fieldnames:
                raise SystemExit(f"column {col!r} not in {fieldnames}")
        rows = list(reader)

    identifier = LanguageIdentifier()
    preds = []
    for start in range(0, len(rows), batch_size):
        chunk = rows[start : start + batch_size]
        preds.extend(identifier.predict([r[text_col] for r in chunk]))

    outdir.mkdir(parents=True, exist_ok=True)
    keep_f = (outdir / f"{input_path.stem}.keep.csv").open("w", newline="", encoding="utf-8")
    disc_f = (outdir / f"{input_path.stem}.discard.csv").open("w", newline="", encoding="utf-8")
    ids_f = (outdir / f"{input_path.stem}.discarded_ids.csv").open("w", newline="", encoding="utf-8")

    keep_w = csv.DictWriter(keep_f, fieldnames=fieldnames)
    keep_w.writeheader()
    disc_w = csv.DictWriter(disc_f, fieldnames=fieldnames + ["pred_lang", "pred_prob"])
    disc_w.writeheader()
    ids_w = csv.writer(ids_f)
    ids_w.writerow([id_col])

    counts = {"keep": 0, "discard": 0}
    for row, pred in zip(rows, preds):
        # keep iff English is the top-1 guess (with optional confidence floor)
        if pred.lang == "eng" and pred.prob >= min_prob:
            keep_w.writerow(row)
            counts["keep"] += 1
        else:
            disc_w.writerow({**row, "pred_lang": pred.label, "pred_prob": f"{pred.prob:.4f}"})
            ids_w.writerow([row[id_col]])
            counts["discard"] += 1

    for f in (keep_f, disc_f, ids_f):
        f.close()
    return counts


def main() -> None:
    p = argparse.ArgumentParser(description="Drop non-English pairs from a (id,text,gloss) CSV.")
    p.add_argument("--input", type=Path, default=Path("data/ASLG-PC12/aslg_pc12.csv"))
    p.add_argument("--outdir", type=Path, default=Path("data/processed"))
    p.add_argument("--text-col", default="text")
    p.add_argument("--id-col", default="id")
    p.add_argument("--min-prob", type=float, default=0.0,
                   help="confidence floor for keeping English (0.0 = trust top-1)")
    p.add_argument("--batch-size", type=int, default=2000)
    args = p.parse_args()

    counts = run(
        args.input, args.outdir,
        text_col=args.text_col, id_col=args.id_col,
        min_prob=args.min_prob, batch_size=args.batch_size,
    )
    total = sum(counts.values()) or 1
    print(f"input: {args.input}  rows: {total}  (min-prob={args.min_prob})", file=sys.stderr)
    print(f"  keep    {counts['keep']:7d}  ({100*counts['keep']/total:5.1f}%)  -> "
          f"{args.outdir}/{args.input.stem}.keep.csv", file=sys.stderr)
    print(f"  discard {counts['discard']:7d}  ({100*counts['discard']/total:5.1f}%)  -> "
          f"{args.outdir}/{args.input.stem}.discard.csv", file=sys.stderr)
    print(f"  discarded ids -> {args.outdir}/{args.input.stem}.discarded_ids.csv", file=sys.stderr)


if __name__ == "__main__":
    main()
