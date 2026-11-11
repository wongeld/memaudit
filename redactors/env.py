"""Reads settings from a .env file.

Looks for .env in the current folder, then in the repository root.
Values already set in the shell are kept, so the shell always wins over .env.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path | None = None) -> Path | None:
    """Load KEY=VALUE lines into os.environ. Returns the file used, or None if none was found."""
    candidates = [path] if path else [Path.cwd() / ".env", REPO_ROOT / ".env"]
    for candidate in candidates:
        if candidate.is_file():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("\"'")
                if value and key not in os.environ:
                    os.environ[key] = value
            return candidate
    return None


def setting(name: str, given: str | None = None) -> str:
    """Return the given value, or the value of name from the shell or .env.

    Raises a clear error if neither is set.
    """
    if given:
        return given
    load_env()
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set. Add it to your .env file (see .env.example).")
    return value
