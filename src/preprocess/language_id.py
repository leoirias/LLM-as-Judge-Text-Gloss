"""Stage 1 — language identification via fastText.

Wraps ``facebook/fasttext-language-identification`` (217 languages, NLLB
labels like ``__label__eng_Latn``). The model is resolved from the local
Hugging Face cache so it works under ``HF_HUB_OFFLINE=1`` inside the
container; download it once on a networked host with
``download_model()`` before running offline.

Note: we always call ``predict`` with a *list* of texts. fastText-wheel's
single-string path runs ``np.array(probs, copy=False)``, which raises under
NumPy 2.x; the list (``multilinePredict``) path skips that, and batches.
"""

from __future__ import annotations

from dataclasses import dataclass

import fasttext
from huggingface_hub import hf_hub_download

_REPO_ID = "facebook/fasttext-language-identification"
_FILENAME = "model.bin"
_LABEL_PREFIX = "__label__"


@dataclass(frozen=True)
class LangPrediction:
    """Top-1 language guess for one text."""

    label: str  # NLLB code, e.g. "eng_Latn" (prefix stripped)
    prob: float

    @property
    def lang(self) -> str:
        """ISO-639-3 part, e.g. "eng" (script dropped)."""
        return self.label.split("_", 1)[0]


def resolve_model_path(*, offline: bool = True) -> str:
    """Return the local path to model.bin from the HF cache.

    With ``offline=True`` (default) it never hits the network; run
    ``download_model()`` first on a host that has connectivity.
    """
    return hf_hub_download(
        repo_id=_REPO_ID,
        filename=_FILENAME,
        local_files_only=offline,
    )


def download_model() -> str:
    """Fetch model.bin into the HF cache (requires network). Returns path."""
    return resolve_model_path(offline=False)


def _clean(text: str) -> str:
    """fastText predicts one line at a time; collapse newlines/whitespace."""
    return " ".join(str(text).split()).strip()


class LanguageIdentifier:
    def __init__(self, model_path: str | None = None) -> None:
        self._path = model_path or resolve_model_path(offline=True)
        self._model = fasttext.load_model(self._path)

    def predict(self, texts: list[str]) -> list[LangPrediction]:
        """Top-1 language for each text, in order. Empty text -> prob 0.0."""
        cleaned = [_clean(t) for t in texts]
        # multilinePredict rejects empty lines; route them around the model.
        idx = [i for i, t in enumerate(cleaned) if t]
        out: list[LangPrediction] = [LangPrediction("und_Zzzz", 0.0)] * len(cleaned)
        if not idx:
            return out
        labels, probs = self._model.predict([cleaned[i] for i in idx], k=1)
        for i, lab, pr in zip(idx, labels, probs):
            out[i] = LangPrediction(lab[0].removeprefix(_LABEL_PREFIX), float(pr[0]))
        return out
