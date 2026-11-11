"""NER-only redactor (C2).

Runs a Hugging Face named-entity model and masks what it finds.
Swahili and Amharic use MasakhaNER. English uses a CoNLL-03 model.

NER only finds names, places, organisations and (MasakhaNER only) dates.
It cannot find phone numbers, emails, ID numbers or addresses.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable

from .base import Redactor, Span

# Model and pinned revision for each language.
# Pinning the revision means the same weights are used on every run.
NER_MODELS: dict[str, tuple[str, str]] = {
    "en": ("dslim/bert-base-NER", "d1a3e8f13f8c3566299d95fcfc9a8d2382a9affc"),
    "sw": ("masakhane/afroxlmr-large-ner-masakhaner-1.0_2.0", "d15d8ba541b2ddf439dc116b50c8a5fa8ace2c48"),
    "am": ("masakhane/afroxlmr-large-ner-masakhaner-1.0_2.0", "d15d8ba541b2ddf439dc116b50c8a5fa8ace2c48"),
}

# Model labels mapped to policy labels.
# MISC (English model only) is not in the redaction policy, so it is dropped.
LABEL_MAP = {"PER": "PERSON", "LOC": "LOCATION", "ORG": "ORGANIZATION", "DATE": "DATE"}

# A pipeline takes text and returns a list of dicts with
# entity_group, score, start and end, as Hugging Face pipelines do.
Pipeline = Callable[[str], list[dict]]


def load_hf_pipeline(model: str, revision: str, device: int = -1) -> Pipeline:
    """Load a Hugging Face token-classification pipeline.

    aggregation_strategy="first" labels whole words, so a name is never split.
    stride lets the pipeline handle texts longer than the model's 512-token limit.
    """
    from transformers import logging as hf_logging
    from transformers import pipeline

    hf_logging.set_verbosity_error()
    hf_logging.disable_progress_bar()
    return pipeline(
        "token-classification",
        model=model,
        revision=revision,
        aggregation_strategy="first",
        stride=64,
        device=device,
    )


class NerDetector:
    """Finds named entities with one model per language.

    Models load the first time a language is used. Swahili and Amharic share
    one MasakhaNER model, so it is loaded once. The Presidio redactor reuses
    this class, so both redactors see exactly the same NER output.
    """

    def __init__(
        self,
        models: dict[str, tuple[str, str]] | None = None,
        min_score: float = 0.5,
        device: int = -1,
        loader: Callable[[str, str], Pipeline] | None = None,
    ) -> None:
        self.models = models or NER_MODELS
        self.min_score = min_score
        self._loader = loader or (lambda model, rev: load_hf_pipeline(model, rev, device))
        self._pipelines: dict[tuple[str, str], Pipeline] = {}

    def model_for(self, lang: str) -> str:
        return self.models[lang][0]

    def _pipeline(self, lang: str) -> Pipeline:
        key = self.models[lang]
        if key not in self._pipelines:
            self._pipelines[key] = self._loader(*key)
        return self._pipelines[key]

    def detect(self, text: str, lang: str) -> list[Span]:
        pipe = self._pipeline(lang)

        # The MasakhaNER tokenizer cannot mark word boundaries directly, so Hugging Face
        # warns and uses a fallback (a new word starts at "▁"). That fallback is correct
        # for this model, so the warning is hidden.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Tokenizer does not support real words")
            entities = pipe(text)

        spans = []
        for ent in entities:
            label = LABEL_MAP.get(ent["entity_group"])
            score = float(ent["score"])
            if label is None or score < self.min_score:
                continue
            start, end = int(ent["start"]), int(ent["end"])
            spans.append(Span(start, end, label, text[start:end], score))
        return spans


class NerRedactor(Redactor):
    """C2: mask only what the NER model finds."""

    name = "ner"

    def __init__(self, detector: NerDetector | None = None) -> None:
        super().__init__()
        self.detector = detector or NerDetector()

    def find_spans(self, text: str, lang: str) -> list[Span]:
        return self.detector.detect(text, lang)
