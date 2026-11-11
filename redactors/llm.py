"""LLM redactor (C3 Gemini, C4 open-weight model).

The model is asked to list the exact pieces of text to mask, each with a label.
It does not rewrite the text. We find each piece in the text and mask it,
so the output looks the same as every other redactor's.
"""

from __future__ import annotations

import json
import os
import re
from typing import Protocol

from .base import LABELS, Redactor, Span, normalize
from .env import setting

SYSTEM_PROMPT = """You find personal information in text so it can be masked.
The text may be in English, Swahili or Amharic.

Mask these, using exactly these labels:
- PERSON: names of people (the speaker, family, friends, colleagues, doctors)
- LOCATION: named places such as towns, neighbourhoods, landmarks
- ORGANIZATION: named employers, schools, hospitals, clinics, churches, mosques, groups
- DATE: specific dates that could identify someone (birth dates, appointment dates)
- PHONE: phone numbers
- EMAIL: email addresses
- ID_NUMBER: national ID, passport, student, patient or account numbers
- ADDRESS: street addresses, house numbers, P.O. boxes

Do NOT mask: occupations, ages, education, family roles (e.g. "my daughter"),
health conditions, vague times (e.g. "yesterday", "every morning"),
or generic places with no name (e.g. "the market", "the hospital").

Return JSON only, in this form:
{"entities": [{"text": "...", "label": "..."}]}

Copy each "text" exactly as it appears, character for character.
List each distinct piece once. If there is nothing to mask, return {"entities": []}."""

USER_TEMPLATE = "Text:\n<<<\n{text}\n>>>"


class LLMClient(Protocol):
    """Anything that can send one prompt and return the reply text."""

    model: str

    def complete(self, system: str, user: str) -> str: ...


class GeminiClient:
    """Google Gemini through the google-genai SDK.

    The model ID and key come from GEMINI_MODEL and GEMINI_API_KEY in .env,
    unless they are passed in directly.
    """

    # The redactor needs a system prompt and a JSON-only reply. The v1beta API supports
    # both; v1 does not, and newer SDK versions default to v1. So v1beta is set here.
    API_VERSION = "v1beta"

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 temperature: float = 0.0) -> None:
        from google import genai
        from google.genai import types

        self.model = setting("GEMINI_MODEL", model)
        self.temperature = temperature
        self._client = genai.Client(
            api_key=setting("GEMINI_API_KEY", api_key),
            http_options=types.HttpOptions(api_version=self.API_VERSION),
        )

    def complete(self, system: str, user: str) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self.temperature,
            response_mime_type="application/json",
        )
        response = self._client.models.generate_content(model=self.model, contents=user, config=config)
        return response.text or ""


class OpenAICompatibleClient:
    """Any OpenAI-compatible server: vLLM, Ollama, or a hosted open-weight model.

    The model name and server come from OPEN_WEIGHT_MODEL and OPEN_WEIGHT_BASE_URL
    in .env, unless they are passed in directly. Local servers usually need no key.
    """

    def __init__(self, model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, temperature: float = 0.0) -> None:
        from openai import OpenAI

        self.model = setting("OPEN_WEIGHT_MODEL", model)
        self.temperature = temperature
        key = api_key or os.environ.get("OPEN_WEIGHT_API_KEY") or "none"
        self._client = OpenAI(base_url=setting("OPEN_WEIGHT_BASE_URL", base_url), api_key=key)

    def complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return response.choices[0].message.content or ""


class LLMOutputError(RuntimeError):
    """The model's reply could not be read as the expected JSON, even after a retry."""


def parse_entities(reply: str) -> list[dict]:
    """Read the model's JSON reply. Accepts code fences and a bare list."""
    cleaned = reply.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned)
    data = json.loads(cleaned)
    if isinstance(data, dict):
        data = data.get("entities")
    if not isinstance(data, list):
        raise ValueError("expected a list of entities")
    return data


def find_occurrences(text: str, piece: str, lang: str) -> list[int]:
    """Start offsets of every occurrence of piece in text.

    For English and Swahili, a match must be a whole word, so "Ann" does not
    match inside "Annual". Amharic attaches prepositions to words ("በአዲስ" =
    "in Addis"), so for Amharic any occurrence counts.
    """
    if lang == "am":
        pattern = re.escape(piece)
    else:
        pattern = rf"(?<!\w){re.escape(piece)}(?!\w)"
    return [m.start() for m in re.finditer(pattern, text)]


class LLMRedactor(Redactor):
    """C3 / C4: ask an LLM which pieces of text to mask."""

    def __init__(self, client: LLMClient, name: str = "llm") -> None:
        super().__init__()
        self.client = client
        self.name = name

    def _ask(self, text: str) -> list[dict]:
        user = USER_TEMPLATE.format(text=text)
        reply = self.client.complete(SYSTEM_PROMPT, user)
        try:
            return parse_entities(reply)
        except (ValueError, json.JSONDecodeError) as first_error:
            # One retry, telling the model what went wrong.
            retry = user + f"\n\nYour previous reply was not valid ({first_error}). Return JSON only."
            reply = self.client.complete(SYSTEM_PROMPT, retry)
            try:
                return parse_entities(reply)
            except (ValueError, json.JSONDecodeError) as error:
                raise LLMOutputError(f"{self.name}: unreadable reply: {reply[:200]!r}") from error

    def find_spans(self, text: str, lang: str) -> list[Span]:
        spans = []
        for item in self._ask(text):
            piece = normalize(str(item.get("text", ""))).strip()
            label = str(item.get("label", "")).upper()
            if not piece:
                continue
            if label not in LABELS:
                self.warn(f"skipped {piece!r}: unknown label {label!r}")
                continue
            starts = find_occurrences(text, piece, lang)
            if not starts:
                self.warn(f"skipped {piece!r} ({label}): not found in the text")
                continue
            for start in starts:
                spans.append(Span(start, start + len(piece), label, piece))
        return spans
