"""Memory notes and memory sets.

Step 2 writes one memory note per redacted session, using only the redacted text:

    memory/<profile_id>_s01_<redactor>.txt

A memory set is a profile's first k notes for one redactor (k = 1, 3, 5, 10). Notes are
written once and reused for every k, so the only difference between k values is how many
sessions the attacker sees.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .sessions import PROFILE_ID_MASK, UUID

SUMMARY_SYSTEM = """You are the long-term memory of a personal AI assistant.
You will read one conversation between a user and the assistant. Write the memory note the
assistant should keep so it can personalise future conversations with this user.

- Write 3 to 8 short bullet points.
- Record what the conversation shows about the user: who they are, their work, family,
  health, routines, plans and preferences.
- Do not add anything that is not in the conversation.
- Some details were masked, for example [PERSON] or [LOCATION]. Keep these placeholders
  exactly as written and do not guess what they hide.
- Write the note in the language the user writes in.

Return only the bullet points."""

SUMMARY_USER = "Conversation:\n<<<\n{conversation}\n>>>"

# File names shared by steps 1 to 4: <profile_id>_s<NN>_<redactor>.txt
FILE_NAME = re.compile(r"^(?P<profile_id>.+)_s(?P<session>\d+)_(?P<redactor>[a-z0-9]+)\.txt$")


def write_note(client, conversation: str) -> str:
    """One memory note for one redacted conversation."""
    reply = client.complete(SUMMARY_SYSTEM, SUMMARY_USER.format(conversation=conversation), json_reply=False)
    return reply.strip()


@dataclass
class MemorySet:
    profile_id: str
    redactor: str
    k: int
    notes: list[str]

    @property
    def key(self) -> str:
        return f"{self.profile_id}|{self.redactor}|{self.k}"

    def as_text(self) -> str:
        """The notes as the attacker sees them: numbered, with no file names or IDs."""
        return "\n\n".join(f"Memory {i}:\n{note.strip()}" for i, note in enumerate(self.notes, start=1))


def read_folder(folder: Path) -> dict[tuple[str, str], dict[int, str]]:
    """(profile_id, redactor) -> {session number: text}, for files named <id>_sNN_<redactor>.txt.

    profile_ids are replaced by [PROFILE_ID] in case any slipped through.
    """
    texts: dict[tuple[str, str], dict[int, str]] = defaultdict(dict)
    if folder.is_dir():
        for path in sorted(folder.glob("*.txt")):
            match = FILE_NAME.match(path.name)
            if match:
                text = UUID.sub(PROFILE_ID_MASK, path.read_text(encoding="utf-8"))
                texts[(match["profile_id"], match["redactor"])][int(match["session"])] = text
    return dict(texts)


def memory_sets(notes: dict[tuple[str, str], dict[int, str]], lengths) -> tuple[list[MemorySet], list[tuple]]:
    """Every memory set that can be built, and the (profile, redactor, k) that cannot.

    A set of length k needs sessions 1 to k. If a profile has fewer, that k is skipped.
    """
    sets, skipped = [], []
    for (profile_id, redactor), by_session in sorted(notes.items()):
        for k in lengths:
            if all(n in by_session for n in range(1, k + 1)):
                sets.append(MemorySet(profile_id, redactor, k, [by_session[n] for n in range(1, k + 1)]))
            else:
                skipped.append((profile_id, redactor, k))
    return sets, skipped
