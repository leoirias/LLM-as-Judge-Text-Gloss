"""Validate extracted rule candidates against the consultancy's gold pairs.

One LLM call per rule: the full list of gold pairs is given at once, and the
model reports which pairs trigger the rule's condition and whether the gold
gloss complies. Classifies each rule as:

  confirmed     - triggered on >=1 pair, all of them comply
  contradicted  - triggered on >=1 pair, none of them comply
  partial       - triggered on >=1 pair, mixed compliance -> needs a human call
  unattested    - never triggered on this gold set

`unattested` is further split by evidence_channel: a "string-checkable" rule
with no matches is just unattested (no text evidence either way). A
"nonmanual"/"spatial" rule can basically never be confirmed from a text-only
gold set, so those are kept separately as video-naturalness reference
material rather than junked as "no evidence" — that signal (facial marking,
spatial verb agreement, etc.) matters once gloss becomes video input, even
if this project's current text-only judge can't check it.

Loads the full model onto the container's assigned GPU — run this yourself
inside the `judge` container:

    docker compose exec judge bash -lc '
      PYTHONPATH=src python extract_rules/validate.py'
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from parsing import extract_json  # noqa: E402
from schema import ExtractedRuleSet, RuleMatchSet  # noqa: E402
import llm as rules_llm  # noqa: E402

from main_pipeline.prompt_loader import load, render  # noqa: E402

HERE = Path(__file__).parent
CFG = yaml.safe_load((HERE / "config.yaml").read_text(encoding="utf-8"))
PROMPT_PATH = HERE / "prompts" / "validate_rule.yaml"

FIELDNAMES = [
    "rule_id", "feature", "trigger", "constraint", "evidence_channel",
    "source_page", "n_matches", "n_comply", "verdict", "examples",
]


def _key(text: str) -> str:
    return " ".join(text.lower().split()).rstrip(" .?!")


def read_gold_pairs(paths: list[Path]) -> list[tuple[str, str]]:
    """Read (text, gloss) pairs, tolerating either pares_ouro.csv-style
    (`Text, Gloss`) or pares_review.csv-style (`Input, Output, Output review`)
    column naming. Prefers the human-reviewed gloss column when present.

    pares_ouro.csv and pares_review.csv are ~99% the same sentences (the
    latter is the former with a handful of glosses corrected), so pairs are
    deduped by normalized text — first file in `paths` wins a given
    sentence. Pass pares_review.csv first to prefer its reviewed gloss."""
    seen: dict[str, tuple[str, str]] = {}
    for path in paths:
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            cols = {c.strip(): c for c in (reader.fieldnames or [])}
            text_col = cols.get("Text") or cols.get("Input") or cols.get("text")
            gloss_col = (
                cols.get("Output review") or cols.get("Gloss")
                or cols.get("Output") or cols.get("gloss")
            )
            if not text_col or not gloss_col:
                raise SystemExit(f"{path}: no text/gloss column in {reader.fieldnames}")
            for row in reader:
                text = (row.get(text_col) or "").strip()
                gloss = (row.get(gloss_col) or "").strip()
                if text and gloss:
                    seen.setdefault(_key(text), (text, gloss))
    return list(seen.values())


def gold_pairs_block(pairs: list[tuple[str, str]]) -> str:
    return "\n".join(f'{i}: "{t}" -> {g}' for i, (t, g) in enumerate(pairs))


def classify(evidence_channel: str, n_total: int, n_comply: int) -> str:
    if n_total == 0:
        return "video_reference" if evidence_channel in ("nonmanual", "spatial") else "unattested"
    if n_comply == n_total:
        return "confirmed"
    if n_comply == 0:
        return "contradicted"
    return "partial"


def main() -> None:
    io_cfg = CFG["io"]
    p = argparse.ArgumentParser()
    p.add_argument("--rules", type=Path, default=Path(io_cfg["rules_out"]))
    p.add_argument("--gold", type=Path, nargs="+",
                    default=[Path(f) for f in io_cfg["gold_files"]])
    p.add_argument("--out", type=Path, default=Path(io_cfg["validation_out"]))
    args = p.parse_args()

    rule_set = ExtractedRuleSet.model_validate_json(args.rules.read_text(encoding="utf-8"))
    pairs = read_gold_pairs(args.gold)
    print(f"[extract_rules] {len(rule_set.rules)} rules, {len(pairs)} gold pairs")
    block = gold_pairs_block(pairs)

    prompt_data = load(str(PROMPT_PATH))
    client = rules_llm.get_llm()

    rows = []
    for rule in rule_set.rules:
        print(f"[extract_rules] validating {rule.id} ...")
        prompt = render(prompt_data, {
            "feature": rule.feature,
            "trigger": rule.trigger,
            "constraint": rule.constraint,
            "exception": rule.exception or "(none)",
            "source_quote": rule.source_quote,
            "source_page": str(rule.source_page),
            "gold_pairs_block": block,
        })
        reply = client.generate(prompt)
        try:
            match_set = RuleMatchSet.model_validate(extract_json(reply))
        except Exception as exc:
            print(f"  ! failed to parse reply for {rule.id}: {exc}")
            match_set = RuleMatchSet(matches=[])

        n_total = len(match_set.matches)
        n_comply = sum(1 for m in match_set.matches if m.complies)
        verdict = classify(rule.evidence_channel, n_total, n_comply)

        rows.append({
            "rule_id": rule.id,
            "feature": rule.feature,
            "trigger": rule.trigger,
            "constraint": rule.constraint,
            "evidence_channel": rule.evidence_channel,
            "source_page": rule.source_page,
            "n_matches": n_total,
            "n_comply": n_comply,
            "verdict": verdict,
            "examples": "; ".join(
                f'#{m.pair_index}:{"OK" if m.complies else "X"}' for m in match_set.matches[:5]
            ),
        })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)
    print(f"[extract_rules] wrote {args.out}")

    by_verdict: dict[str, int] = {}
    for r in rows:
        by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1
    print("[extract_rules] summary:", by_verdict)


if __name__ == "__main__":
    main()
