"""Redact saved sessions into one text file per redactor.

Run from this directory:

    python main.py
    python main.py --sessions sessions --output-dir redacted
    python main.py --lang sw

Each session produces four files: ``none``, ``ner``, ``presidio`` and
``gemini``. Only user and assistant text content is included; event metadata,
assistant thinking, signatures and tool events are omitted.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from redactors.base import LANGUAGES, NoRedaction, Redactor
from redactors.env import load_env
from redactors.llm import GeminiClient, LLMRedactor
from redactors.ner import NerDetector, NerRedactor
from redactors.presidio_redactor import PresidioRedactor


@dataclass(frozen=True)
class Turn:
    role: str
    text: str


def extract_turns(path: Path) -> list[Turn]:
    """Extract complete user/assistant text messages from a session JSONL file."""
    turns: list[Turn] = []
    with path.open(encoding="utf-8") as session:
        for line_number, line in enumerate(session, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path.name}:{line_number}: invalid JSON: {error}") from error

            if event.get("type") != "message_end":
                continue
            message = event.get("message", {})
            role = message.get("role")
            if role not in {"user", "assistant"}:
                continue

            text_parts = [
                item.get("text", "")
                for item in message.get("content", [])
                if item.get("type") == "text" and isinstance(item.get("text"), str)
            ]
            text = "".join(text_parts).strip()
            if text:
                turns.append(Turn(role, text))
    return turns


def detect_language(turns: list[Turn]) -> str:
    """Detect Amharic from its script and otherwise use Swahili for these sessions."""
    combined = "\n".join(turn.text for turn in turns)
    if any("\u1200" <= character <= "\u137f" for character in combined):
        return "am"
    return "sw"


def transcript(turns: list[Turn]) -> str:
    """Render a clean chat transcript without event-level metadata."""
    return "\n\n".join(f"{turn.role.title()}:\n{turn.text}" for turn in turns)


def build_redactors() -> list[Redactor]:
    """Build all required redactors, sharing one NER detector."""
    detector = NerDetector()
    return [
        NoRedaction(),
        NerRedactor(detector),
        PresidioRedactor(detector),
        LLMRedactor(GeminiClient(), name="gemini"),
    ]


def redact_sessions(
    sessions_dir: Path,
    output_dir: Path,
    language: str | None = None,
) -> int:
    """Redact every JSONL session and return the number of source sessions processed."""
    session_files = sorted(sessions_dir.glob("*.jsonl"))
    if not session_files:
        raise FileNotFoundError(f"no .jsonl session files found in {sessions_dir}")

    load_env()
    redactors = build_redactors()
    output_dir.mkdir(parents=True, exist_ok=True)

    for session_file in session_files:
        turns = extract_turns(session_file)
        if not turns:
            raise ValueError(f"{session_file.name}: no user or assistant text found")
        lang = language or detect_language(turns)
        text = transcript(turns)

        for redactor in redactors:
            result = redactor.redact(text, lang)
            output_file = output_dir / f"{session_file.stem}_{redactor.name}.txt"
            output_file.write_text(result.redacted + "\n", encoding="utf-8")
            for warning in result.warnings:
                safe_warning = warning.encode("ascii", "backslashreplace").decode("ascii")
                print(f"warning: {session_file.name} ({redactor.name}): {safe_warning}")

        print(f"redacted {session_file.name} ({lang})")
    return len(session_files)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Redact saved JSONL sessions into clean text files.")
    parser.add_argument(
        "--sessions",
        type=Path,
        default=Path(__file__).resolve().parent / "sessions",
        help="directory containing session JSONL files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "redacted",
        help="directory for the four text files per session",
    )
    parser.add_argument("--lang", choices=LANGUAGES, help="override automatic language detection")
    args = parser.parse_args(argv)

    count = redact_sessions(args.sessions, args.output_dir, args.lang)
    print(f"wrote {count * 4} redacted text files to {args.output_dir}")


if __name__ == "__main__":
    main()
