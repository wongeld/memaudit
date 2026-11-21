"""LLM redactor (C3 Gemini, C4 open-weight model).

The model is asked to list the exact pieces of text to mask, each with a label.
It does not rewrite the text. We find each piece in the text and mask it,
so the output looks the same as every other redactor's.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
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

    def complete(self, system: str, user: str, json_reply: bool = True) -> str: ...


class DailyQuotaReached(RuntimeError):
    """The model's daily (free-tier) quota is used up. Run again after it resets."""


# HTTP status codes worth retrying: rate limit and temporary server errors.
RETRY_STATUS = {429, 500, 502, 503, 504}


def _status(error: Exception):
    return getattr(error, "code", None) or getattr(error, "status_code", None)


def with_retries(call, attempts: int = 6, first_wait: float = 5.0):
    """Run call(). On a rate limit or temporary server error, wait and try again.

    Waits 5, 10, 20, 40 and 80 seconds between tries. A used-up daily quota stops at once,
    because waiting minutes will not help. Other errors, such as a bad key or an unknown
    model, are raised straight away.
    """
    for attempt in range(attempts):
        try:
            return call()
        except Exception as error:
            status = _status(error)
            if status == 429 and ("PerDay" in str(error) or "per day" in str(error).lower()):
                raise DailyQuotaReached(
                    "The model's daily quota is used up. Everything finished so far is saved; "
                    "run the same command again after the quota resets (for Gemini: midnight Pacific time)."
                ) from None
            temporary = status in RETRY_STATUS or "Timeout" in type(error).__name__ \
                or "Connection" in type(error).__name__
            if not temporary or attempt == attempts - 1:
                raise
            wait = first_wait * 2 ** attempt
            print(f"  {type(error).__name__} ({status}); waiting {wait:.0f}s and retrying", file=sys.stderr)
            time.sleep(wait)


class Throttle:
    """Keeps calls at least 60 / rpm seconds apart, to stay under a requests-per-minute limit."""

    def __init__(self, rpm: float | None) -> None:
        self.gap = 60.0 / rpm if rpm else 0.0
        self.last = 0.0

    def wait(self) -> None:
        pause = self.last + self.gap - time.monotonic()
        if pause > 0:
            time.sleep(pause)
        self.last = time.monotonic()


def _rpm(prefix: str) -> float | None:
    value = os.environ.get(f"{prefix}_RPM", "").strip()
    return float(value) if value else None


class GeminiClient:
    """A model on the Gemini API (Gemini or Gemma) through the google-genai SDK.

    Settings are read from .env using a prefix. With the default prefix GEMINI:
        GEMINI_MODEL, GEMINI_API_KEY, GEMINI_RPM (optional requests-per-minute limit).
    With prefix ATTACKER: ATTACKER_MODEL, ATTACKER_RPM, and ATTACKER_API_KEY or else GEMINI_API_KEY.
    """

    # The redactor needs a system prompt and a JSON-only reply. The v1beta API supports
    # both; v1 does not, and newer SDK versions default to v1. So v1beta is set here.
    API_VERSION = "v1beta"

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 temperature: float = 0.0, prefix: str = "GEMINI") -> None:
        from google import genai
        from google.genai import types

        self.model = setting(f"{prefix}_MODEL", model)
        self.temperature = temperature
        key = api_key or os.environ.get(f"{prefix}_API_KEY") or setting("GEMINI_API_KEY")
        self._client = genai.Client(api_key=key, http_options=types.HttpOptions(api_version=self.API_VERSION))
        self._throttle = Throttle(_rpm(prefix))
        # Some models on this API (e.g. Gemma) refuse a separate system prompt or JSON mode.
        # After the first refusal the instructions are sent inside the message instead.
        self._plain = False

    def _send(self, system: str, user: str, json_reply: bool):
        from google.genai import types

        if self._plain:
            config = types.GenerateContentConfig(temperature=self.temperature)
            contents = f"{system}\n\n{user}"
        else:
            config = types.GenerateContentConfig(
                system_instruction=system, temperature=self.temperature,
                response_mime_type="application/json" if json_reply else None,
            )
            contents = user
        self._throttle.wait()
        return with_retries(
            lambda: self._client.models.generate_content(model=self.model, contents=contents, config=config)
        )

    def complete(self, system: str, user: str, json_reply: bool = True) -> str:
        try:
            response = self._send(system, user, json_reply)
        except Exception as error:
            if self._plain or _status(error) != 400 or "not enabled" not in str(error):
                raise
            self._plain = True
            response = self._send(system, user, json_reply)
        return response.text or ""


class OpenAICompatibleClient:
    """Any OpenAI-compatible API: Mistral, OpenRouter, Groq, vLLM, Ollama, ...

    Settings are read from .env using a prefix. With the default prefix OPEN_WEIGHT:
        OPEN_WEIGHT_MODEL, OPEN_WEIGHT_BASE_URL, OPEN_WEIGHT_API_KEY, OPEN_WEIGHT_RPM.
    Local servers usually need no key.
    """

    def __init__(self, model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, temperature: float = 0.0, prefix: str = "OPEN_WEIGHT") -> None:
        from openai import OpenAI

        self.model = setting(f"{prefix}_MODEL", model)
        self.temperature = temperature
        key = api_key or os.environ.get(f"{prefix}_API_KEY") or "none"
        self._client = OpenAI(base_url=setting(f"{prefix}_BASE_URL", base_url), api_key=key, max_retries=0)
        self._throttle = Throttle(_rpm(prefix))

    def complete(self, system: str, user: str, json_reply: bool = True) -> str:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        self._throttle.wait()
        response = with_retries(
            lambda: self._client.chat.completions.create(
                model=self.model, temperature=self.temperature, messages=messages
            )
        )
        return response.choices[0].message.content or ""


def client_for(role: str) -> LLMClient:
    """The model for a role (SUMMARIZER or ATTACKER), chosen in .env:

        <ROLE>_PROVIDER   gemini (default; uses GEMINI_API_KEY) or openai (any OpenAI-compatible API)
        <ROLE>_MODEL      model ID
        <ROLE>_BASE_URL   API address, for provider openai
        <ROLE>_API_KEY    key, if different from GEMINI_API_KEY or needed by the provider
        <ROLE>_RPM        optional requests-per-minute limit
    """
    provider = os.environ.get(f"{role}_PROVIDER", "gemini").strip().lower()
    if provider == "gemini":
        return GeminiClient(prefix=role)
    if provider == "openai":
        return OpenAICompatibleClient(prefix=role)
    raise RuntimeError(f"{role}_PROVIDER must be gemini or openai, not {provider!r}")


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
