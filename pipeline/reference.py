"""Reference spans: where the personal information is in each session's text.

These are the answer key for the span-level precision, recall and F1 of the redactors.
They are found automatically, because every identifier in the synthetic data comes from
the profile or from the user's own requests:

    NAME          the profile's first name, last name and full name
    PHONE         the profile's phone number, in any spacing
    EMAIL         the profile's email address
    NATIONAL_ID   the profile's national ID number
    LOCATION      the profile's city, country and neighbourhood
    PLACE         named places the user asked the assistant to search for
    COORDINATES   latitude and longitude numbers the user gave

Ages, occupations, education, family status, health and times of day are not in the
answer key: the redaction policy leaves them in on purpose.

Names and places are always in Latin script in this data, including in Amharic sessions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .profiles import Profile
from .sessions import Session

KINDS = ("NAME", "PHONE", "EMAIL", "NATIONAL_ID", "LOCATION", "PLACE", "COORDINATES")

DIGIT_RUN = re.compile(r"\+?\d[\d\s().-]{5,}\d")


@dataclass(frozen=True)
class RefSpan:
    start: int
    end: int
    kind: str
    text: str


def _words(text: str, phrase: str, kind: str) -> list[RefSpan]:
    """Every whole-word, case-insensitive occurrence of a phrase.

    Only Latin letters and digits count as word edges, because in Amharic text a name is
    often written straight after a Ge'ez prefix (e.g. "በAddis Ababa" = "in Addis Ababa").
    """
    if len(phrase) < 2:
        return []
    pattern = rf"(?<![A-Za-z0-9]){re.escape(phrase)}(?![A-Za-z0-9])"
    return [RefSpan(m.start(), m.end(), kind, m.group()) for m in re.finditer(pattern, text, re.IGNORECASE)]


def _digits(text: str, number: str, kind: str, match_end: bool) -> list[RefSpan]:
    """Digit runs (spaces, dashes and brackets allowed inside) that contain the number.

    Phones match on their last 9 digits, so "+254 122 951 015" and "0122951015" both count.
    """
    wanted = re.sub(r"\D", "", number)
    if match_end:
        wanted = wanted[-9:]
    if len(wanted) < 6:
        return []
    spans = []
    for m in DIGIT_RUN.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if (digits.endswith(wanted) if match_end else digits == wanted):
            spans.append(RefSpan(m.start(), m.end(), kind, m.group()))
    return spans


def reference_spans(text: str, profile: Profile, session: Session) -> list[RefSpan]:
    """All reference spans in one session's transcript, without overlaps.

    When two spans overlap (e.g. the city "Embu" inside the place "Kangaru School Embu"),
    the longer one is kept.
    """
    found: list[RefSpan] = []
    found += _words(text, profile.name, "NAME")
    found += _words(text, profile.first_name, "NAME")
    found += _words(text, profile.last_name, "NAME")
    found += _digits(text, profile.phone, "PHONE", match_end=True)
    if profile.email:
        found += [RefSpan(m.start(), m.end(), "EMAIL", m.group())
                  for m in re.finditer(re.escape(profile.email), text, re.IGNORECASE)]
    found += _digits(text, profile.national_id, "NATIONAL_ID", match_end=False)
    for place in (profile.city, profile.country, profile.neighborhood):
        found += _words(text, place, "LOCATION")
    for place in session.places:
        found += _words(text, place, "PLACE")
    for number in session.coordinates:
        pattern = rf"(?<![\d.]){re.escape(number)}(?![\d])"
        found += [RefSpan(m.start(), m.end(), "COORDINATES", m.group()) for m in re.finditer(pattern, text)]

    kept: list[RefSpan] = []
    for span in sorted(found, key=lambda s: (-(s.end - s.start), s.start)):
        if all(span.end <= k.start or span.start >= k.end for k in kept):
            kept.append(span)
    return sorted(kept, key=lambda s: s.start)
