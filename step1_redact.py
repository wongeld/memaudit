"""Step 1: redact every session with every redactor.

    python step1_redact.py
    python step1_redact.py --redactors none,ner,presidio     without Gemini (no API calls)
    python step1_redact.py --force                           redo files that already exist

Reads   sessions/*.jsonl and profiles/profiles.csv
Writes  redacted/<profile_id>_s01_<redactor>.txt          the redacted session
        redacted/<profile_id>_s01_<redactor>.spans.json   where the masks are (for scoring)
        redacted/index.csv                                one row per file

Sessions are cut as set by SESSION_SIZE in config.py. Files that already exist are skipped,
so when new sessions arrive, running this again only redacts (and pays for) the new ones.
"""

from __future__ import annotations

import argparse
import csv
import json
import re

import config
from pipeline.profiles import load_profiles
from pipeline.sessions import PROFILE_ID_MASK, detect_language, load_sessions, user_text
from redactors.base import NoRedaction, Redactor
from redactors.env import load_env

ALL = ("none", "ner", "presidio", "gemini", "open")

# Output files from the first version of main.py (one file per profile, no session number).
OLD_FILE = re.compile(r"^[0-9a-f-]{36}_[a-z]+\.txt$")


def build_redactors(names: list[str]) -> list[Redactor]:
    """The requested redactors. NER and Presidio share one NER model."""
    from redactors.ner import NerDetector, NerRedactor
    from redactors.presidio_redactor import PresidioRedactor

    detector = NerDetector()
    built: list[Redactor] = []
    for name in names:
        if name == "none":
            built.append(NoRedaction())
        elif name == "ner":
            built.append(NerRedactor(detector))
        elif name == "presidio":
            built.append(PresidioRedactor(detector))
        elif name == "gemini":
            from redactors.llm import GeminiClient, LLMRedactor
            built.append(LLMRedactor(GeminiClient(), name="gemini"))
        elif name == "open":
            from redactors.llm import LLMRedactor, OpenAICompatibleClient
            built.append(LLMRedactor(OpenAICompatibleClient(), name="open"))
        else:
            raise SystemExit(f"Unknown redactor {name!r}. Choose from: {', '.join(ALL)}")
    return built


def safe(text: str) -> str:
    """Printable on any terminal (some Windows consoles cannot show Ge'ez script)."""
    return text.encode("ascii", "backslashreplace").decode("ascii")


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 1: redact every session with every redactor.")
    parser.add_argument("--redactors", default=",".join(config.REDACTORS),
                        help=f"comma-separated, from: {', '.join(ALL)} (default: {','.join(config.REDACTORS)})")
    parser.add_argument("--force", action="store_true", help="redo files that already exist")
    args = parser.parse_args()

    load_env()
    profiles = load_profiles()
    all_sessions = load_sessions()
    redactors = build_redactors([n.strip() for n in args.redactors.split(",") if n.strip()])
    out_dir = config.REDACTED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # Record which model each LLM redactor used, for the report.
    models_file = out_dir / "models.json"
    models = json.loads(models_file.read_text(encoding="utf-8")) if models_file.exists() else {}
    models.update({r.name: r.client.model for r in redactors if hasattr(r, "client")})
    models_file.write_text(json.dumps(models, indent=1), encoding="utf-8")

    old = [p for p in out_dir.iterdir() if OLD_FILE.match(p.name)]
    if old:
        print(f"Note: {len(old)} files in redacted/ are from the old one-file-per-profile format. "
              "They are ignored; you can delete them.\n")

    split = f"{config.SESSION_SIZE} user messages" if config.SESSION_SIZE else "self-introductions"
    print(f"{len(all_sessions)} session files; sessions cut by {split}; "
          f"redactors: {', '.join(r.name for r in redactors)}\n")

    index, new_files = [], 0
    for profile_id, sessions in all_sessions.items():
        profile = profiles.get(profile_id)
        detected = detect_language(user_text(sessions))
        if profile is None:
            lang = detected
            print(f"Warning: {profile_id} is not in profiles.csv; using detected language {lang}.")
        else:
            lang = profile.language
            if detected != lang:
                print(f"Warning: {profile_id} is {lang} in profiles.csv but its text looks like {detected}.")
        complete = [s for s in sessions if s.complete]
        print(f"{profile_id}  {lang}  {len(complete)} sessions"
              + (f"  ({len(sessions) - len(complete)} incomplete skipped)" if len(complete) < len(sessions) else ""))

        for session in complete:
            text = session.transcript()
            for redactor in redactors:
                stem = f"{session.stem}_{redactor.name}"
                txt, spans = out_dir / f"{stem}.txt", out_dir / f"{stem}.spans.json"
                if args.force or not (txt.exists() and spans.exists()):
                    try:
                        result = redactor.redact(text, lang)
                    except Exception as error:
                        message = (f"\nStopped at {stem}: {safe(str(error))}\n"
                                   "Files written so far are kept; run the same command again to continue.")
                        raise SystemExit(message) from None
                    txt.write_text(result.redacted, encoding="utf-8")
                    spans.write_text(json.dumps(
                        [{"start": s.start, "end": s.end, "label": s.label, "text": s.text} for s in result.spans],
                        ensure_ascii=False, indent=0), encoding="utf-8")
                    new_files += 1
                    for warning in result.warnings:
                        print(f"   warning ({redactor.name}, session {session.number}): {safe(warning)}")
                masks = len(json.loads(spans.read_text(encoding="utf-8")))
                index.append({"profile_id": profile_id, "session": session.number, "lang": lang,
                              "redactor": redactor.name, "user_messages": session.user_messages,
                              "masks": masks, "file": txt.name})

    with (out_dir / "index.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(index[0]) if index else ["file"])
        writer.writeheader()
        writer.writerows(index)
    print(f"\nDone. {new_files} new files; {len(index)} listed in redacted/index.csv. "
          f"{PROFILE_ID_MASK} replaces every profile_id before redaction.")


if __name__ == "__main__":
    main()
