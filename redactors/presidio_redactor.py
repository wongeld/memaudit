"""Presidio redactor (C1).

Presidio's pattern recognizers (email, phone number, date) plus the same NER
model used by the NER-only redactor, plugged into Presidio as a recognizer.
The only difference between C1 and C2 is therefore Presidio's pattern rules.

Presidio needs a tokenizer for each language. We give it a blank spaCy
pipeline (tokenizer only), so no spaCy model download is needed and every
named entity comes from our NER model.
"""

from __future__ import annotations

from .base import LANGUAGES, Redactor, Span
from .ner import NerDetector

# Blank spaCy tokenizer per language. spaCy has no Swahili module,
# so Swahili uses the multi-language tokenizer "xx".
SPACY_BLANK = {"en": "en", "sw": "xx", "am": "am"}

# Phone regions tried by Presidio's phone recognizer.
# Kenya, Tanzania, Uganda and Ethiopia first, then Presidio's usual defaults.
PHONE_REGIONS = ("KE", "TZ", "UG", "ET", "US", "GB")

# Presidio entity names mapped to policy labels.
PRESIDIO_TO_POLICY = {
    "PERSON": "PERSON",
    "LOCATION": "LOCATION",
    "ORGANIZATION": "ORGANIZATION",
    "DATE_TIME": "DATE",
    "PHONE_NUMBER": "PHONE",
    "EMAIL_ADDRESS": "EMAIL",
}

# NER labels mapped to the Presidio entity names our recognizer reports.
POLICY_TO_PRESIDIO = {"PERSON": "PERSON", "LOCATION": "LOCATION",
                      "ORGANIZATION": "ORGANIZATION", "DATE": "DATE_TIME"}


def _build_analyzer(detector: NerDetector):
    """Build a Presidio AnalyzerEngine for en, sw and am."""
    import spacy
    from presidio_analyzer import AnalyzerEngine, EntityRecognizer, RecognizerRegistry, RecognizerResult
    from presidio_analyzer.nlp_engine import SpacyNlpEngine
    from presidio_analyzer.predefined_recognizers import (
        DateRecognizer,
        EmailRecognizer,
        PhoneRecognizer,
    )

    class BlankSpacyEngine(SpacyNlpEngine):
        """Presidio NLP engine that only tokenizes. It finds no entities itself."""

        def load(self) -> None:
            self.nlp = {lang: spacy.blank(code) for lang, code in SPACY_BLANK.items()}

    class NerRecognizer(EntityRecognizer):
        """Wraps NerDetector so Presidio can use it like any other recognizer."""

        def __init__(self, lang: str) -> None:
            super().__init__(
                supported_entities=list(POLICY_TO_PRESIDIO.values()),
                supported_language=lang,
                name=f"NerRecognizer_{lang}",
            )

        def load(self) -> None:
            pass

        def analyze(self, text, entities, nlp_artifacts=None):
            results = []
            for span in detector.detect(text, self.supported_language):
                entity = POLICY_TO_PRESIDIO[span.label]
                if entity in entities:
                    results.append(RecognizerResult(entity, span.start, span.end, span.score))
            return results

    engine = BlankSpacyEngine(models=[{"lang_code": lang, "model_name": "blank"} for lang in LANGUAGES])
    engine.load()

    # Presidio recognizers are tied to one language, so we add one set per language.
    registry = RecognizerRegistry(supported_languages=list(LANGUAGES))
    for lang in LANGUAGES:
        registry.add_recognizer(EmailRecognizer(supported_language=lang))
        registry.add_recognizer(PhoneRecognizer(supported_language=lang, supported_regions=PHONE_REGIONS))
        registry.add_recognizer(DateRecognizer(supported_language=lang))
        registry.add_recognizer(NerRecognizer(lang))

    return AnalyzerEngine(nlp_engine=engine, registry=registry, supported_languages=list(LANGUAGES))


class PresidioRedactor(Redactor):
    """C1: Presidio pattern recognizers plus the shared NER model."""

    name = "presidio"

    def __init__(self, detector: NerDetector | None = None, score_threshold: float = 0.0) -> None:
        super().__init__()
        self.detector = detector or NerDetector()
        self.score_threshold = score_threshold
        self._analyzer = None

    def _get_analyzer(self):
        if self._analyzer is None:
            self._analyzer = _build_analyzer(self.detector)
        return self._analyzer

    def find_spans(self, text: str, lang: str) -> list[Span]:
        results = self._get_analyzer().analyze(
            text=text,
            language=lang,
            entities=list(PRESIDIO_TO_POLICY),
            score_threshold=self.score_threshold,
        )
        return [
            Span(r.start, r.end, PRESIDIO_TO_POLICY[r.entity_type], text[r.start:r.end], r.score)
            for r in results
        ]
