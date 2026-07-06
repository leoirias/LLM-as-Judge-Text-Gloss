"""Stage 2 (B2) — mojibake / encoding (error E2).

ftfy fixes the common cases deterministically; whatever still looks corrupted
is rebuilt from the aligned clean token in the English `text`
(VURAL à?GER + text "vural öger" -> VURAL OGER). Unrecoverable -> flagged.
"""

from __future__ import annotations

import re

import ftfy

from pipeline_hybrid.align import align, fold_ascii

# a token is "corrupted" if it still has non-ASCII, a replacement char, a
# stray '?' glued inside a word, or a backtick.
_CORRUPT = re.compile(r"[^\x00-\x7F]|�|[A-Za-z]\?[A-Za-z]|\?[A-Z]|`")


def is_corrupt(tok: str) -> bool:
    return bool(_CORRUPT.search(tok))


def fix(text: str, gloss: str) -> tuple[str, bool]:
    """Return (repaired_gloss, recovered_ok). recovered_ok=False -> needs human."""
    g = ftfy.fix_text(gloss)
    toks = g.split()
    if not any(is_corrupt(t) for t in toks):
        return g, True

    aligned = align(text, toks, fuzz_min=62)  # lenient: corrupt tokens align loosely
    ok = True
    out: list[str] = []
    for a in aligned:
        if not is_corrupt(a.gloss):
            out.append(a.gloss)
        elif a.token is not None:
            out.append(fold_ascii(a.token.text))  # rebuild from clean source
        else:
            out.append(fold_ascii(a.gloss))       # best-effort fold
            ok = False                            # couldn't anchor -> low conf
    return " ".join(out), ok
