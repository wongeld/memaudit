"""Step 2: write one memory note for every redacted session.

    python step2_memory.py --dry-run                 show the plan and one prompt; no API calls
    python step2_memory.py --limit 3                 pilot: the first 3 profiles of each language
    python step2_memory.py                           everything
    python step2_memory.py --redactors none,presidio only what Tables 2 and 3 need

Reads   redacted/<profile_id>_s01_<redactor>.txt
Writes  memory/<profile_id>_s01_<redactor>.txt

The summarizer sees only the redacted session, never the profile. Its model is set in .env
(SUMMARIZER_PROVIDER, SUMMARIZER_MODEL). Notes that already exist are skipped, so a stopped
run continues where it left off.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict

import config
from pipeline.memory import SUMMARY_SYSTEM, SUMMARY_USER, read_folder, write_note
from pipeline.profiles import load_profiles
from redactors.env import load_env


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 2: write one memory note per redacted session.")
    parser.add_argument("--redactors", help="comma-separated; default: every redactor in redacted/")
    parser.add_argument("--limit", type=int, help="only the first N profiles of each language (pilot)")
    parser.add_argument("--dry-run", action="store_true", help="show the plan and one prompt; no API calls")
    args = parser.parse_args()

    load_env()
    profiles = load_profiles()
    redacted = read_folder(config.REDACTED_DIR)
    if not redacted:
        raise SystemExit("No redacted sessions found. Run step1_redact.py first.")
    if args.redactors:
        wanted = {r.strip() for r in args.redactors.split(",")}
        redacted = {k: v for k, v in redacted.items() if k[1] in wanted}
    if args.limit:
        by_lang: dict[str, list[str]] = defaultdict(list)
        for pid in sorted({pid for pid, _ in redacted}):
            by_lang[profiles[pid].language if pid in profiles else "?"].append(pid)
        keep = {pid for ids in by_lang.values() for pid in ids[:args.limit]}
        redacted = {k: v for k, v in redacted.items() if k[0] in keep}

    config.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    todo = [(pid, red, n, text) for (pid, red), sessions in sorted(redacted.items())
            for n, text in sorted(sessions.items())
            if not (config.MEMORY_DIR / f"{pid}_s{n:02d}_{red}.txt").exists()]
    total = sum(len(s) for s in redacted.values())
    print(f"{total} redacted sessions; {total - len(todo)} notes already written; {len(todo)} to write.")

    if args.dry_run:
        if todo:
            pid, red, n, text = todo[0]
            print(f"\n--- system prompt ---\n{SUMMARY_SYSTEM}\n\n--- message for {pid} session {n} ({red}) ---")
            message = SUMMARY_USER.format(conversation=text)
            print(message if len(message) < 2500 else message[:2500] + "\n[...]")
        return
    if not todo:
        return

    from redactors.llm import DailyQuotaReached, client_for

    client = client_for("SUMMARIZER")
    print(f"Summarizer: {client.model}\n")
    (config.MEMORY_DIR / "models.json").write_text(json.dumps({"summarizer": client.model}), encoding="utf-8")
    for i, (pid, red, n, text) in enumerate(todo, start=1):
        try:
            note = write_note(client, text)
        except DailyQuotaReached as error:
            raise SystemExit(f"\n{error}") from None
        except Exception as error:
            raise SystemExit(f"\nStopped at {pid} session {n} ({red}): {error}\n"
                             "Notes written so far are kept; run the same command again to continue.") from None
        (config.MEMORY_DIR / f"{pid}_s{n:02d}_{red}.txt").write_text(note, encoding="utf-8")
        print(f"[{i}/{len(todo)}] {pid} s{n:02d} {red}")
    print("\nDone. Notes are in memory/.")


if __name__ == "__main__":
    main()
