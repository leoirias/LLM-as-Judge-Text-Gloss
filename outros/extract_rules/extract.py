"""Extract candidate ASL grammar rules from a book chapter using the LLM.

Loads the full model onto the container's assigned GPU — run this yourself
inside the `judge` container, not delegated to an agent:

    docker compose exec judge bash -lc '
      PYTHONPATH=src python extract_rules/extract.py'

Uses --start-page/--end-page (0-indexed, matching the PDF outline / see
config.yaml) to default to Chapter 2 ("Signing Grammar Basics").
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from outros.extract_rules.parsing import extract_json  # noqa: E402
from outros.extract_rules.pdf_text import extract_pages  # noqa: E402
from outros.extract_rules.schema import ExtractedRuleSet  # noqa: E402
import outros.extract_rules.llm as rules_llm  # noqa: E402

from main_pipeline.prompt_loader import load, render  # noqa: E402

HERE = Path(__file__).parent
CFG = yaml.safe_load((HERE / "config.yaml").read_text(encoding="utf-8"))
PROMPT_PATH = HERE / "prompts" / "extract_rules.yaml"


def main() -> None:
    book_cfg = CFG["book"]
    p = argparse.ArgumentParser()
    p.add_argument("--book", type=Path, default=Path(book_cfg["path"]))
    p.add_argument("--start-page", type=int, default=int(book_cfg["start_page"]))
    p.add_argument("--end-page", type=int, default=int(book_cfg["end_page"]))
    p.add_argument("--out", type=Path, default=Path(CFG["io"]["rules_out"]))
    args = p.parse_args()

    chapter_text = extract_pages(args.book, args.start_page, args.end_page)
    print(f"[extract_rules] {len(chapter_text)} chars from pages "
          f"{args.start_page}-{args.end_page} of {args.book}")

    prompt_data = load(str(PROMPT_PATH))
    prompt = render(prompt_data, {"chapter_text": chapter_text})

    print("[extract_rules] loading qwen3-32b (thinking on) ...")
    client = rules_llm.get_llm()
    print("[extract_rules] generating rules — this can take several minutes ...")
    reply = client.generate(prompt)

    payload = extract_json(reply)
    rule_set = ExtractedRuleSet.model_validate(payload)
    print(f"[extract_rules] extracted {len(rule_set.rules)} candidate rules")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rule_set.model_dump_json(indent=2), encoding="utf-8")
    print(f"[extract_rules] wrote {args.out}")


if __name__ == "__main__":
    main()
