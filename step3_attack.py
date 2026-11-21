"""Step 3: run the two attacks on every memory set.

    python step3_attack.py --dry-run                 show the plan and one prompt of each attack; no API calls
    python step3_attack.py --limit 3                 pilot: the first 3 profiles of each language
    python step3_attack.py                           everything
    python step3_attack.py --redactors none,presidio only what Tables 2 and 3 need
    python step3_attack.py --task identify           one attack only (attributes or identify)

Reads   memory/<profile_id>_s01_<redactor>.txt and profiles/profiles.csv
Writes  results/attacks/attributes.jsonl and results/attacks/identify.jsonl, one line per query

For each profile, redactor and memory length k (MEMORY_LENGTHS in config.py), the attacker
reads the first k memory notes. Its model is set in .env (ATTACKER_PROVIDER, ATTACKER_MODEL).
Answers already saved are skipped, so a stopped run continues where it left off.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import config
from pipeline.attacks import (
    attribute_options,
    attribute_prompt,
    candidate_pool,
    identification_prompt,
    identify_profile,
    recover_attributes,
    shuffled,
)
from pipeline.memory import memory_sets, read_folder
from pipeline.profiles import load_profiles
from redactors.env import load_env

TASKS = ("attributes", "identify")
OUT_DIR = config.RESULTS_DIR / "attacks"


def saved(path: Path) -> set[str]:
    """Keys of the queries already in a results file. Stops if they used another candidate pool."""
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    other = {r.get("pool") for r in records} - {config.CANDIDATE_POOL}
    if other:
        raise SystemExit(f"{path} holds answers made with CANDIDATE_POOL = {other}. "
                         "Move that file away before running with a different pool.")
    return {r["key"] for r in records}


def show(prompt: str) -> str:
    """Start of a long prompt (the notes) and its end (the options or candidates)."""
    if len(prompt) <= 3000:
        return prompt
    return prompt[:700] + "\n\n[... rest of the notes left out here ...]\n\n" + prompt[-2200:]


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 3: attribute-recovery and identification attacks.")
    parser.add_argument("--task", choices=TASKS, help="run only this attack")
    parser.add_argument("--redactors", help="comma-separated; default: every redactor in memory/")
    parser.add_argument("--limit", type=int, help="only the first N profiles of each language (pilot)")
    parser.add_argument("--memory-dir", type=Path, default=config.MEMORY_DIR,
                        help="where the notes are (default memory/). 'redacted' tests with redacted sessions.")
    parser.add_argument("--dry-run", action="store_true", help="show the plan and one prompt; no API calls")
    args = parser.parse_args()

    load_env()
    profiles = load_profiles()
    notes = read_folder(args.memory_dir)
    if not notes:
        raise SystemExit(f"No notes found in {args.memory_dir}. Run step2_memory.py first.")
    unknown = sorted({pid for pid, _ in notes} - set(profiles))
    if unknown:
        print(f"Skipping {len(unknown)} profiles that are not in profiles.csv: {unknown}")
    notes = {k: v for k, v in notes.items() if k[0] in profiles}
    if args.redactors:
        wanted = {r.strip() for r in args.redactors.split(",")}
        notes = {k: v for k, v in notes.items() if k[1] in wanted}
    if args.limit:
        by_lang: dict[str, list[str]] = defaultdict(list)
        for pid in sorted({pid for pid, _ in notes}):
            by_lang[profiles[pid].language].append(pid)
        keep = {pid for ids in by_lang.values() for pid in ids[:args.limit]}
        notes = {k: v for k, v in notes.items() if k[0] in keep}

    sets, skipped = memory_sets(notes, config.MEMORY_LENGTHS)
    tasks = [args.task] if args.task else list(TASKS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = {t: OUT_DIR / f"{t}.jsonl" for t in tasks}
    done = {t: saved(p) for t, p in outputs.items()}
    todo = [(t, s) for t in tasks for s in sets if s.key not in done[t]]

    langs = Counter(profiles[pid].language for pid in {s.profile_id for s in sets})
    missing_k = Counter(k for _, _, k in skipped)
    print(f"Profiles attacked: {', '.join(f'{n} {config.LANGUAGE_NAMES[lang]}' for lang, n in langs.items())}")
    print(f"Redactors: {', '.join(sorted({s.redactor for s in sets}))}")
    print(f"Memory sets: {len(sets)}; lengths available: {sorted({s.k for s in sets})}")
    for k, n in sorted(missing_k.items()):
        print(f"  k={k}: skipped for {n} profile/redactor pairs with fewer than {k} sessions")
    print(f"Candidate pool: {config.CANDIDATE_POOL}")
    print(f"Queries to run: {len(todo)} (already saved: {sum(len(d) for d in done.values())})\n")

    if args.dry_run:
        for task in tasks:
            example = next((s for t, s in todo if t == task), None)
            if example:
                pool = candidate_pool(profiles[example.profile_id], profiles)
                prompt = (attribute_prompt(example, attribute_options(pool)) if task == "attributes"
                          else identification_prompt(example, shuffled(pool, example)))
                print(f"--- example {task} prompt ({example.key}), {len(prompt)} characters ---\n{show(prompt)}\n")
        return
    if not todo:
        print("Nothing to do.")
        return

    from redactors.llm import DailyQuotaReached, client_for

    client = client_for("ATTACKER")
    print(f"Attacker: {client.model}\n")
    for i, (task, memory) in enumerate(todo, start=1):
        target = profiles[memory.profile_id]
        pool = candidate_pool(target, profiles)
        started = time.perf_counter()
        try:
            record = (recover_attributes(client, memory, attribute_options(pool)) if task == "attributes"
                      else identify_profile(client, memory, pool))
        except DailyQuotaReached as error:
            raise SystemExit(f"\n{error}") from None
        except Exception as error:
            raise SystemExit(f"\nStopped at {task} {memory.key}: {error}\n"
                             "Answers saved so far are kept; run the same command again to continue.") from None
        record = {"key": memory.key, "profile_id": memory.profile_id, "lang": target.language,
                  "redactor": memory.redactor, "k": memory.k, "pool": config.CANDIDATE_POOL,
                  "pool_size": len(pool), "memory": args.memory_dir.name, "model": client.model,
                  "seconds": round(time.perf_counter() - started, 2), **record}
        with outputs[task].open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        note = "  (reply could not be read; counted as wrong)" if record["parse_error"] else ""
        print(f"[{i}/{len(todo)}] {task:10} {target.language} {memory.redactor:8} k={memory.k:<2} "
              f"{memory.profile_id}{note}")
    print("\nDone. Answers are in results/attacks/.")


if __name__ == "__main__":
    main()
