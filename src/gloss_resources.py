"""Shared resources for both normalization pipelines (B1 LLM-only, B2 hybrid).

Single source of truth for the convention, mirroring plain.md:
- COMPOUNDS  — Part C (real consultancy compounds, underscore)
- FEWSHOT    — curated gold pairs from pares_ouro.csv anchoring the convention
- rule text blocks (E2-E6, R1-R15) reused verbatim inside prompts
- extract_gloss() — robustly pull the final gloss out of a model reply
"""

from __future__ import annotations

# --- Part C: real compounds (underscore). Sequence = separate signs. ---------
COMPOUNDS: list[str] = [
    "HOW_MUCH", "NO_PROBLEM", "NOT_UNDERSTAND", "PASS_OUT",
    "THANK_YOU", "THIS_MORNING", "WRITE_DOWN",
]

# --- curated few-shot from data/pares_ouro.csv (covers each rule family) ------
FEWSHOT: list[tuple[str, str]] = [
    ("You need antibiotics", "NEED ANTIBIOTIC"),
    ("I will call the doctor", "CALL DOCTOR"),
    ("You can go home tomorrow", "TOMORROW CAN GO HOME"),
    ("The blood test is ready now", "NOW BLOOD TEST READY"),
    ("Do you have shortness of breath?", "HAVE PROBLEM BREATH?"),
    ("When did your fever start?", "FEVER START WHEN?"),
    ("How are you feeling now?", "NOW FEEL HOW?"),
    ("How are you?", "HOW YOU?"),
    ("Where are you?", "WHERE YOU?"),
    ("When did you vomit?", "WHEN VOMIT FINISH?"),
    ("I fell this morning", "THIS_MORNING FALL"),
    ("Thank you", "THANK_YOU"),
]


def fewshot_block(pairs: list[tuple[str, str]] | None = None) -> str:
    pairs = pairs or FEWSHOT
    return "\n".join(f'Text: "{t}"  ->  Gloss: {g}' for t, g in pairs)


# --- rule text (referenced by the prompts of both pipelines) -----------------
KNOWN_ERRORS = """\
E2 Mojibake/encoding: fix garbled chars using the English text as reference
   (e.g. Ha?kmark -> HOKMARK). Unrecoverable -> keep best guess.
E3 Wrong prefix: remove DESC-, X-, G- (the convention uses no prefix).
E4 Typo/truncated token: fix it (gyneclogist -> GYNECOLOGIST,
   nerlands -> NETHERLANDS) using the sentence meaning.
E5 Abbreviation: expand it (LAB -> LABORATORY, SEC -> SECOND).
E6 Bad compound: real compound -> underscore; otherwise two signs
   (BLOOD-TEST -> BLOOD TEST)."""

TOKEN_RULES = """\
R1 Everything UPPERCASE.
R2 Remove articles (the, a, an).
R2b Remove prepositions (for, of, to, with, in, from, about)
    - e.g. READY FOR HOSPITAL -> READY HOSPITAL; SHORTNESS OF BREATH -> ...BREATH.
    Do NOT remove quantifiers (any, some, all, many) - they stay
    (HAVE ALLERGIC ANY MEDICINE).
R3 Remove linking copula "be" - ALL forms (is, are, am, was, were, be, been, being).
R4 Remove question auxiliaries (do, does, did).
R4b Remove AUXILIARY have/has/had in perfect tenses (have been submitted -> SUBMIT;
    has gone -> GO). KEEP possessive/content HAVE (do you have pain -> HAVE PAIN).
R5 Remove subject pronoun (I, YOU). EXCEPTION: keep it when the sentence has
   no lexical verb (HOW YOU?, WHERE YOU?, NOW YOU PAIN STRONG?) or the pronoun
   is an object (NICE MEET YOU).
R6 Remove possessive (YOUR, MY) - including body part/condition
   (YOUR PNEUMONIA -> PNEUMONIA).
R7 Singular noun, COMMON NOUNS ONLY (ANTIBIOTICS -> ANTIBIOTIC). NEVER change a
   proper name (person/place/organization), even if it ends in -s: keep it
   exactly as in the English text (JAMES ELLES stays JAMES ELLES, NETHERLANDS
   stays NETHERLANDS, BRUSSELS stays BRUSSELS). A trailing -s on a name is part
   of the name, not a plural.
R8 Base-form verb, ALWAYS (MOVING -> MOVE, SUBMITTED -> SUBMIT, FELL -> FALL);
   tense becomes a marker in R13.
R9 Mark real compounds with underscore (list: %s)."""  % " ".join(COMPOUNDS)

REORDER_RULES = """\
R10 Time to the front - NOW, TODAY, TOMORROW, THIS_MORNING go to the start
    (...READY NOW -> NOW ... READY).
R11 WH position:
    - DEFAULT: WH goes to the END, after the verb (When did your fever start?
      -> FEVER START WHEN?; How are you feeling now? -> NOW FEEL HOW?).
    - EXCEPTION: verbless question (copula dropped, only WH + a noun) -> WH at
      the FRONT (How are you? -> HOW YOU?; What time is it? -> WHAT TIME?;
      How much is this? -> HOW_MUCH THIS?).
    - Topicalization: topic to the front with a comma, WH stays at the end of
      the comment (Where do you feel pain from the accident?
      -> ACCIDENT, PAIN WHERE FEEL?).
R12 Keep content verbs and modals - HAVE, FEEL, CAN do not drop
    (Can you breathe? -> CAN BREATHE?).
R13 Mark past/completed with FINISH (and PAST) - (When did you vomit?
    -> WHEN VOMIT FINISH?).
R14 Conceptual sign choice, not literal (shortness of breath -> PROBLEM BREATH).
R15 Keep punctuation by sentence type (. statement, ? question)."""


def extract_gloss(reply: str) -> str:
    """Pull the gloss out of a model reply, tolerating preamble/markers."""
    text = (reply or "").strip()
    if not text:
        return ""
    # strip a leading "GLOSS:" style label if present
    for marker in ("GLOSS:", "Gloss:", "gloss:", "OUTPUT:", "Output:"):
        if marker in text:
            text = text.split(marker, 1)[1].strip()
    # take the last non-empty line (models sometimes add a trailing note first)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[-1].strip().strip('"').strip() if lines else ""
