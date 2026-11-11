"""Redactors for the memaudit study. Import them from scripts in the repository folder.

    none      C0  baseline, masks nothing
    presidio  C1  Presidio pattern recognizers + NER model
    ner       C2  NER model only (MasakhaNER for sw/am)
    gemini    C3  LLM redactor using Gemini
    open      C4  LLM redactor using an open-weight model

Every redactor has the same method. lang is "en", "sw" or "am".
result.redacted is the text with [LABEL] masks; result.spans lists what was masked.

    result = redactor.redact(text, lang)
"""

from .base import LABELS, LANGUAGES, NoRedaction, RedactionResult, Redactor, Span
from .llm import GeminiClient, LLMRedactor, OpenAICompatibleClient
from .ner import NerDetector, NerRedactor
from .presidio_redactor import PresidioRedactor

__all__ = [
    "LABELS", "LANGUAGES", "Span", "RedactionResult", "Redactor",
    "NoRedaction", "NerDetector", "NerRedactor", "PresidioRedactor",
    "LLMRedactor", "GeminiClient", "OpenAICompatibleClient",
]
