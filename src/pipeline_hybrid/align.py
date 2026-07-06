"""ALIGN (B2 shared) — parse the English `text` with spaCy and map each gloss
token to its source token, so the gloss (which has no grammar) can borrow
POS / lemma / tag / tense from the text.

Used by: mojibake (recover a corrupted token from its clean source) and clean
(singularize R7 / base-verb R8 only when the source token really is a plural
noun / verb — which also prevents wrongly singularizing names like JAMES).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

import spacy
from rapidfuzz import fuzz
from spacy.tokens import Token

_FUZZ_MIN = 80.0
_ALNUM = re.compile(r"[^A-Z0-9]")


@lru_cache(maxsize=1)
def get_nlp():
    # only tagger/lemmatizer/parser needed; keep it light
    return spacy.load("en_core_web_sm", disable=["ner"])


def fold_ascii(s: str) -> str:
    """Accents/diacritics -> plain ASCII upper (öger -> OGER)."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).upper()


@dataclass
class Aligned:
    gloss: str            # the gloss token (as given)
    token: Token | None   # matched spaCy token in `text`, or None
    method: str           # exact | lemma | fuzzy | none
    score: float = 0.0    # fuzzy score (100 for exact/lemma)


def parse(text: str):
    return get_nlp()(text)


def align(text: str, gloss_tokens: list[str], *, fuzz_min: float = _FUZZ_MIN) -> list[Aligned]:
    doc = parse(text)
    cand = [t for t in doc if not t.is_punct and not t.is_space]
    by_text: dict[str, Token] = {}
    by_lemma: dict[str, Token] = {}
    for t in cand:
        by_text.setdefault(t.text.lower(), t)
        by_lemma.setdefault(t.lemma_.lower(), t)

    out: list[Aligned] = []
    for g in gloss_tokens:
        key = g.lower().strip("_-")
        if not key:
            out.append(Aligned(g, None, "none"))
            continue
        if key in by_text:
            out.append(Aligned(g, by_text[key], "exact", 100.0))
        elif key in by_lemma:
            out.append(Aligned(g, by_lemma[key], "lemma", 100.0))
        else:
            # compare on alphanumeric-only folded forms so mojibake/typos
            # (à?GER, REFORE) still anchor to their clean source (OGER, THEREFORE)
            best, score = None, 0.0
            kf = _ALNUM.sub("", fold_ascii(key))
            for t in cand:
                s = fuzz.ratio(kf, _ALNUM.sub("", fold_ascii(t.text)))
                if s > score:
                    best, score = t, s
            out.append(Aligned(g, best, "fuzzy", score) if score >= fuzz_min
                       else Aligned(g, None, "none", score))
    return out
