"""Shared resources for the main pipeline: gold few-shot, compound list, and
the gloss extractor. Everything here is grounded in the consultancy gold pairs.
"""

from __future__ import annotations

# real compounds (underscore). A compositional sequence stays as separate signs.
COMPOUNDS: list[str] = [
    "HOW_MUCH", "NO_PROBLEM", "NOT_UNDERSTAND", "PASS_OUT",
    "THANK_YOU", "THIS_MORNING", "WRITE_DOWN",
]

# curated few-shot from data/pares_ouro.csv (one per rule family), used by P3
FEWSHOT: list[tuple[str, str]] = [
    ("You need antibiotics", "NEED ANTIBIOTIC"),
    ("I will call the doctor", "CALL DOCTOR"),
    ("You can go home tomorrow", "TOMORROW CAN GO HOME"),
    ("I feel dizzy today", "TODAY FEEL DIZZY"),
    ("Do you have shortness of breath?", "HAVE PROBLEM BREATH?"),
    ("When did your fever start?", "FEVER START WHEN?"),
    ("How are you feeling now?", "NOW FEEL HOW?"),
    ("How are you?", "HOW YOU?"),
    ("When did you vomit?", "WHEN VOMIT FINISH?"),
    ("I fell this morning", "THIS_MORNING FALL"),
]


def _key(s: str) -> str:
    return " ".join((s or "").lower().split()).rstrip(" .?!")


def fewshot_block(
    pairs: list[tuple[str, str]] | None = None,
    exclude: set[str] | None = None,
) -> str:
    """Render the few-shot block, dropping any example whose text is in the test
    set (`exclude` = set of input texts). Guarantees few-shot ∩ test = ∅."""
    pairs = pairs or FEWSHOT
    ex = {_key(t) for t in (exclude or set())}
    chosen = [(t, g) for t, g in pairs if _key(t) not in ex]
    return "\n".join(f'Text: "{t}"  ->  Gloss: {g}' for t, g in chosen)


def extract_gloss(reply: str) -> str:
    """Pull the gloss out of a model reply, tolerating preamble/markers."""
    text = (reply or "").strip()
    if not text:
        return ""
    for marker in ("GLOSS:", "Gloss:", "gloss:", "OUTPUT:", "Output:", "Result gloss:"):
        if marker in text:
            text = text.split(marker, 1)[1].strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[-1].strip().strip('"').strip() if lines else ""
