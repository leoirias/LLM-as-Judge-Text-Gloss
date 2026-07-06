"""Main pipeline (LLM-only) — normalize an ASL gloss to the consultancy
convention in stages, one prompt per stage (P1 errors, P2 clean, P3 reorder,
optional P4 validate). Language filtering is preprocessing, not part of this.
"""
