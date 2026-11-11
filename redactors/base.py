"""Shared pieces used by every redactor.

A redactor only finds spans of personal information. Masking happens here,
in one function, so every redactor writes masks in exactly the same way.
"""

from __future__ import annotations

import time
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# Labels from the redaction policy. Every redactor maps its own labels to these.
LABELS = ("PERSON", "LOCATION", "ORGANIZATION", "DATE", "PHONE", "EMAIL", "ID_NUMBER", "ADDRESS")

LANGUAGES = ("en", "sw", "am")

MASK_FORMAT = "[{label}]"

# Characters trimmed from the edges of a detected span.
# NER models often attach trailing punctuation to the last word ("Wanjiru.").
EDGE_CHARS = " \t\n.,;:!?\"'()[]“”‘’።፣፤፥፦"


@dataclass(frozen=True)
class Span:
    """A piece of text to mask. start and end are character offsets."""

    start: int
    end: int
    label: str
    text: str
    score: float | None = None


@dataclass
class RedactionResult:
    """Everything one redactor produced for one text."""

    redactor: str
    lang: str
    original: str
    redacted: str
    spans: list[Span]
    seconds: float
    warnings: list[str] = field(default_factory=list)


def normalize(text: str) -> str:
    """Unicode NFC. Amharic can be written with different code-point sequences that look the same."""
    return unicodedata.normalize("NFC", text)


def trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Shrink a span so it does not start or end with spaces or punctuation."""
    while start < end and text[start] in EDGE_CHARS:
        start += 1
    while end > start and text[end - 1] in EDGE_CHARS:
        end -= 1
    return start, end


def merge_spans(spans: list[Span], text: str) -> list[Span]:
    """Sort spans and join any that overlap or touch.

    When two spans join, the label of the longer one is kept.
    """
    ordered = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))
    merged: list[Span] = []
    for span in ordered:
        if merged and span.start <= merged[-1].end:
            last = merged[-1]
            longer = last if (last.end - last.start) >= (span.end - span.start) else span
            end = max(last.end, span.end)
            merged[-1] = Span(last.start, end, longer.label, text[last.start:end], longer.score)
        else:
            merged.append(span)
    return merged


def mask_text(text: str, spans: list[Span], mask_format: str = MASK_FORMAT) -> str:
    """Replace each span with its mask. Spans must already be merged and sorted."""
    parts: list[str] = []
    cursor = 0
    for span in spans:
        parts.append(text[cursor:span.start])
        parts.append(mask_format.format(label=span.label))
        cursor = span.end
    parts.append(text[cursor:])
    return "".join(parts)


class Redactor(ABC):
    """Base class. Subclasses implement find_spans; redact does the rest."""

    name = "base"

    def __init__(self) -> None:
        self._warnings: list[str] = []

    @abstractmethod
    def find_spans(self, text: str, lang: str) -> list[Span]:
        """Return the spans to mask. Offsets refer to the NFC-normalised text."""

    def warn(self, message: str) -> None:
        """Record a problem that should be visible in the result, not hidden."""
        self._warnings.append(message)

    def redact(self, text: str, lang: str) -> RedactionResult:
        if lang not in LANGUAGES:
            raise ValueError(f"lang must be one of {LANGUAGES}, got {lang!r}")
        self._warnings = []
        text = normalize(text)

        started = time.perf_counter()
        found = self.find_spans(text, lang)
        seconds = time.perf_counter() - started

        # Check every span before masking, so a bug in a redactor fails loudly.
        clean: list[Span] = []
        for span in found:
            if span.label not in LABELS:
                raise ValueError(f"{self.name}: unknown label {span.label!r}")
            if not 0 <= span.start < span.end <= len(text):
                raise ValueError(f"{self.name}: span {span} is outside the text")
            start, end = trim_span(text, span.start, span.end)
            if start < end:
                clean.append(Span(start, end, span.label, text[start:end], span.score))

        spans = merge_spans(clean, text)
        return RedactionResult(
            redactor=self.name,
            lang=lang,
            original=text,
            redacted=mask_text(text, spans),
            spans=spans,
            seconds=seconds,
            warnings=list(self._warnings),
        )


class NoRedaction(Redactor):
    """Baseline (C0). Masks nothing."""

    name = "none"

    def find_spans(self, text: str, lang: str) -> list[Span]:
        return []
