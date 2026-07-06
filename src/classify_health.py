"""Classify aslg-pc12 sentences by health domain with qwen3-32B.

Sentence by sentence (one prompt per sentence; batched only for throughput),
passing ONLY the `text` field. tqdm shows progress + ETA. Resumable: re-running
skips ids already in the output file. Any extra input columns (e.g. gloss) are
carried through to the output.

Two modes:
  --mode domain    (broad) is the sentence about health/medicine at all?
  --mode clinical  (strict) is it an INDIVIDUAL's medical situation, like the
                   consultancy gold (patient/doctor: symptoms, diagnosis,
                   treatment) - NOT health policy/legislation/debate?

    PYTHONPATH=src python -m classify_health --mode domain \
        --input data/processed/aslg_pc12.keep.csv \
        --output data/processed/health_flags.csv

    PYTHONPATH=src python -m classify_health --mode clinical \
        --input data/processed/health_yes.csv \
        --output data/processed/health_clinical.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from tqdm import tqdm

from main_pipeline.llm import generate_batch, get_llm

PROMPT_DOMAIN = """You classify a sentence by topic domain.

Is the sentence below about HEALTH or MEDICINE? This includes: health policy,
public health, diseases/illness, patients, hospitals/clinics, doctors/nurses,
medical care or treatment, medicines/drugs/vaccines, epidemics/pandemics,
mental health, and health-related disability.

Answer with ONE word only: YES or NO.

Sentence: "{text}"
Answer:"""

PROMPT_CLINICAL = """You classify a sentence.

Answer YES only if the sentence describes an INDIVIDUAL PERSON'S health or
medical situation - symptoms, a diagnosis, a treatment, medication for a person,
or a clinical / doctor-patient exchange (e.g. "you need antibiotics",
"do you have chest pain?", "I have high blood pressure", "the doctor will check
your blood test").

Answer NO if it is about health POLICY, legislation, institutions/agencies,
public-health programmes, or a general debate about health topics - i.e. NOT one
person's concrete medical situation.

Answer with ONE word only: YES or NO.

Sentence: "{text}"
Answer:"""

PROMPTS = {"domain": PROMPT_DOMAIN, "clinical": PROMPT_CLINICAL}


def parse_yesno(reply: str) -> str:
    r = (reply or "").strip().upper()
    for tok in r.replace(".", " ").replace(",", " ").split():
        if tok.startswith("YES"):
            return "YES"
        if tok.startswith("NO"):
            return "NO"
    return "?"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=Path("data/processed/aslg_pc12.keep.csv"))
    ap.add_argument("--output", type=Path, default=Path("data/processed/health_flags.csv"))
    ap.add_argument("--mode", choices=list(PROMPTS), default="domain")
    ap.add_argument("--limit", type=int, default=0, help="process only the first N rows (0 = all)")
    ap.add_argument("--batch-size", type=int, default=16)
    args = ap.parse_args()
    prompt_tpl = PROMPTS[args.mode]

    reader = csv.DictReader(args.input.open(newline="", encoding="utf-8"))
    in_cols = reader.fieldnames or ["id", "text"]
    rows = list(reader)
    if args.limit:
        rows = rows[: args.limit]

    # carry through input columns (id, text, and gloss if present) + health flag
    out_cols = [c for c in in_cols if c != "health"] + ["health"]

    done: set[str] = set()
    if args.output.exists():
        for r in csv.DictReader(args.output.open(newline="", encoding="utf-8")):
            done.add(r["id"])
    todo = [r for r in rows if r["id"] not in done]
    print(f"mode={args.mode}  total={len(rows)}  done={len(done)}  to do={len(todo)}")
    if not todo:
        print("nothing to do.")
        return

    llm = get_llm()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    new_file = not args.output.exists()
    fh = args.output.open("a", newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=out_cols)
    if new_file:
        w.writeheader()
        fh.flush()

    bs = args.batch_size
    pbar = tqdm(total=len(todo), unit="sent", desc=f"classify:{args.mode}")
    for start in range(0, len(todo), bs):
        chunk = todo[start : start + bs]
        prompts = [prompt_tpl.format(text=r["text"]) for r in chunk]
        replies = generate_batch(llm, prompts, chunk=bs)
        for r, rep in zip(chunk, replies):
            w.writerow({**{c: r.get(c, "") for c in out_cols if c != "health"},
                        "health": parse_yesno(rep)})
        fh.flush()
        pbar.update(len(chunk))
    pbar.close()
    fh.close()
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
