"""Stage 3 (B2) — token-by-token cleaning: errors E3-E6 + rules R1-R9.

Deterministic, with spaCy doing the grammar-aware bits (R5 via dependency,
R7/R8 via POS+lemma). The sentence-level rules R10-R15 are NOT here — they go
to the LLM in reorder.py.
"""

from __future__ import annotations

import re

from gloss_resources import COMPOUNDS
from pipeline_hybrid.align import align, fold_ascii, parse

PREFIX = re.compile(r"^(DESC|X|G)-", re.IGNORECASE)

ARTICLES = {"THE", "A", "AN"}
# prepositions attested as dropped in pares_ouro (28/29 rows). Conservative on
# purpose: only the ones the gold actually shows dropping, so contentful preps
# like AGAINST stay until the gold provides evidence.
PREP = {"FOR", "OF", "TO", "WITH", "IN", "FROM", "ABOUT"}
COPULA = {"BE", "BEEN", "BEING", "IS", "ARE", "AM", "WAS", "WERE"}
AUX_Q = {"DO", "DOES", "DID"}
SUBJ_PRON = {"I", "YOU"}
AUX_HAVE = {"HAVE", "HAS", "HAD"}  # drop only when auxiliary (perfect); content HAVE stays
POSS = {"YOUR", "MY", "MINE", "OUR", "POSS"}  # POSS = glosser's possessive artifact
ABBREV = {"LAB": "LABORATORY", "SEC": "SECOND"}
_E4_MIN = 88.0  # confidence to fix a typo/truncation from the aligned source

SUBJ_DEPS = {"nsubj", "nsubjpass", "expl"}
_COMPOUND_PARTS = [(c, c.split("_")) for c in COMPOUNDS]  # ("THANK_YOU", ["THANK","YOU"])


_PUNCT = re.compile(r"^([.,;:!?]*)(.*?)([.,;:!?]*)$")


def _split_punct(piece: str) -> list[str]:
    """Peel leading/trailing punctuation into their own tokens (R15: preserve)."""
    m = _PUNCT.match(piece)
    lead, core, trail = m.groups()
    return [t for t in (lead, core, trail) if t]


def _pretokenize(gloss: str) -> list[str]:
    """E3 (strip prefix), R1 (upper), E6 (hyphen -> split), punctuation kept as
    its own token so it is never rewritten/dropped downstream."""
    out: list[str] = []
    for raw in gloss.split():
        tok = PREFIX.sub("", raw).upper()
        for piece in (tok.split("-") if "-" in tok else [tok]):  # BLOOD-TEST -> BLOOD TEST
            if piece:
                out.extend(_split_punct(piece))
    return out


def _join_compounds(tokens: list[str]) -> list[str]:
    """R9 — merge real compound part-sequences into one underscore sign."""
    out, i = [], 0
    while i < len(tokens):
        matched = False
        for joined, parts in _COMPOUND_PARTS:
            n = len(parts)
            if tokens[i : i + n] == parts:
                out.append(joined)
                i += n
                matched = True
                break
        if not matched:
            out.append(tokens[i])
            i += 1
    return out


def clean(text: str, gloss: str) -> str:
    tokens = _join_compounds(_pretokenize(gloss))
    has_lexical_verb = any(t.pos_ == "VERB" for t in parse(text))
    aligned = align(text, tokens)

    out: list[str] = []
    for a in aligned:
        tok = a.gloss
        if "_" in tok:                       # finished compound: keep as-is
            out.append(tok)
            continue
        if tok in ARTICLES or tok in COPULA or tok in AUX_Q or tok in POSS or tok in PREP:
            continue                          # R2 / R3 / R4 / R6 / preposition
        if tok in AUX_HAVE and a.token is not None and a.token.pos_ == "AUX":
            continue                          # drop auxiliary have/has/had (perfect)
        if tok in SUBJ_PRON:                  # R5 (+ exception)
            t = a.token
            is_object = t is not None and t.dep_ not in SUBJ_DEPS and t.dep_ != "ROOT"
            if has_lexical_verb and not is_object:
                continue                      # drop subject pronoun
            out.append(tok)                   # keep (verbless or object)
            continue
        if tok in ABBREV:                     # E5
            out.append(ABBREV[tok])
            continue
        t = a.token
        if t is None:
            out.append(tok)
        elif a.method == "fuzzy" and a.score >= _E4_MIN:
            out.append(fold_ascii(t.text))    # E4 typo/truncation -> clean source
        elif t.pos_ == "NOUN" and t.tag_ == "NNS":
            out.append(t.lemma_.upper())      # R7 plural noun -> singular
        elif t.pos_ == "VERB":
            out.append(t.lemma_.upper())      # R8 verb -> base form
        else:
            out.append(tok)                   # keep (incl. proper names: no R7)
    return _detok(out)


def _detok(tokens: list[str]) -> str:
    """Join with spaces, but attach punctuation to the previous token."""
    s = ""
    for t in tokens:
        if re.fullmatch(r"[.,;:!?]+", t):
            s += t
        else:
            s += (" " + t) if s else t
    return s
