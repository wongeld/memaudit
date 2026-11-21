"""Reading the generated session files and cutting them into sessions.

Each file in sessions/ holds one profile's whole history, in order. The file name is
the profile_id. How the history is cut into sessions is set by SESSION_SIZE in config.py.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import config

# A profile_id is a UUID. It is a key used by the data generator's tools, not something a
# real user would say, so it is replaced with [PROFILE_ID] in every condition before redaction.
UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
PROFILE_ID_MASK = "[PROFILE_ID]"

# Common function words, used to tell English from Swahili.
# Amharic is recognised by its script (Ge'ez, U+1200 to U+137F).
ENGLISH_WORDS = {"the", "and", "to", "of", "my", "for", "please", "is", "in", "with", "i", "a", "it", "on"}
SWAHILI_WORDS = {"na", "ya", "kwa", "wa", "ni", "za", "la", "kama", "tafadhali", "naomba", "mimi",
                 "yangu", "hii", "katika", "kwenye", "ili", "hiyo", "wangu", "kuwa"}


@dataclass(frozen=True)
class Turn:
    role: str
    text: str


@dataclass
class Session:
    profile_id: str
    number: int
    turns: list[Turn]
    complete: bool = True
    places: list[str] = field(default_factory=list)
    coordinates: list[str] = field(default_factory=list)

    @property
    def user_messages(self) -> int:
        return sum(1 for t in self.turns if t.role == "user")

    @property
    def stem(self) -> str:
        """File name stem used by every step: <profile_id>_s01."""
        return f"{self.profile_id}_s{self.number:02d}"

    def transcript(self) -> str:
        """The conversation as plain text, NFC-normalised, with profile_ids replaced."""
        text = "\n\n".join(f"{t.role.title()}:\n{t.text}" for t in self.turns)
        return unicodedata.normalize("NFC", UUID.sub(PROFILE_ID_MASK, text))


def read_turns(path: Path) -> list[Turn]:
    """Complete user and assistant text messages from one session file.

    Event metadata, assistant thinking, tool calls and tool results are left out.
    """
    turns: list[Turn] = []
    with path.open(encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise SystemExit(f"{path.name}:{line_number}: invalid JSON: {error}") from None
            if event.get("type") != "message_end":
                continue
            message = event.get("message", {})
            if message.get("role") not in {"user", "assistant"}:
                continue
            text = "".join(
                item.get("text", "") for item in message.get("content", [])
                if item.get("type") == "text" and isinstance(item.get("text"), str)
            ).strip()
            if text:
                turns.append(Turn(message["role"], text))
    return turns


def _session_starts(profile_id: str, turns: list[Turn], size: int | None) -> list[int]:
    """Index of the first turn of each session."""
    user_positions = [i for i, t in enumerate(turns) if t.role == "user"]
    if size:
        return user_positions[::size]
    marker = re.compile(rf"profile_id:\s*{re.escape(profile_id)}", re.IGNORECASE)
    starts = [i for i in user_positions if marker.search(turns[i].text)]
    return starts or user_positions[:1]


def searched_places(turns: list[Turn]) -> list[str]:
    """Named places the user asked the assistant to look up, e.g. 'Kangaru School Embu'.

    They appear in quotes in user messages that mention search_places.
    """
    places = []
    for t in turns:
        if t.role == "user" and "search_places" in t.text:
            places += [q.strip() for q in re.findall(r"['‘’\"“”]([^'‘’\"“”]{3,80})['‘’\"“”]", t.text)]
    return list(dict.fromkeys(p for p in places if p))


def coordinates(turns: list[Turn]) -> list[str]:
    """Latitude and longitude numbers the user gave, e.g. -0.5143 and 37.4589."""
    found = []
    for t in turns:
        if t.role == "user":
            found += re.findall(r"(?:latitude|longitude)\D{0,12}?(-?\d{1,3}\.\d{2,})", t.text, re.IGNORECASE)
    return list(dict.fromkeys(found))


def split_sessions(profile_id: str, turns: list[Turn], size: int | None = config.SESSION_SIZE) -> list[Session]:
    """Cut one profile's turns into sessions.

    With a fixed size, a last session with fewer user messages is marked incomplete.
    With size None, sessions start where the user introduces themselves.
    """
    starts = _session_starts(profile_id, turns, size)
    if not starts:
        return []
    starts[0] = 0
    bounds = starts + [len(turns)]
    sessions = []
    for n in range(len(starts)):
        chunk = turns[bounds[n]:bounds[n + 1]]
        session = Session(profile_id, n + 1, chunk, places=searched_places(chunk), coordinates=coordinates(chunk))
        if size:
            session.complete = session.user_messages == size
        sessions.append(session)
    if not size and len(sessions) > 1:
        usual = max(s.user_messages for s in sessions)
        for s in sessions:
            s.complete = s.user_messages >= usual
    return sessions


def load_sessions(folder: Path = config.SESSIONS_DIR) -> dict[str, list[Session]]:
    """profile_id -> its sessions in order, for every .jsonl file in the folder."""
    files = sorted(folder.glob("*.jsonl"))
    if not files:
        raise SystemExit(f"No .jsonl session files found in {folder}")
    return {f.stem: split_sessions(f.stem, read_turns(f)) for f in files}


def detect_language(text: str) -> str:
    """Guess "am", "sw" or "en" for a text."""
    if sum(1 for ch in text if "ሀ" <= ch <= "፿") > 20:
        return "am"
    words = re.findall(r"[a-z]+", text.lower())
    english = sum(1 for w in words if w in ENGLISH_WORDS)
    swahili = sum(1 for w in words if w in SWAHILI_WORDS)
    return "en" if english > swahili else "sw"


def user_text(sessions: list[Session]) -> str:
    return "\n".join(t.text for s in sessions for t in s.turns if t.role == "user")
