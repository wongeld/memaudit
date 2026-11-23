"""Step 5: measure synthetic candidate reduction using saved Step 3 answers."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import config
from pipeline.attacks import INVALID, UNKNOWN, normalize
from pipeline.memory import memory_sets, read_folder
from pipeline.profiles import Profile, load_profiles

OUT = config.ROOT / "simulation" / "reduction"
STAGES = ("location", "occupation", "education")


def read_records(path: Path, required: bool = True) -> dict[str, dict]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Missing Step 3 results: {path}")
        return {}
    records = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            key = record["key"]
            if key in records:
                raise ValueError(f"{path}: duplicate case {key} at line {line_number}")
            records[key] = record
    if required and not records:
        raise ValueError(f"No Step 3 answers found in {path}")
    return records


def validate_case(record: dict, profiles: dict[str, Profile]) -> None:
    key = f"{record['profile_id']}|{record['redactor']}|{record['k']}"
    if record["key"] != key or record["profile_id"] not in profiles:
        raise ValueError(f"Invalid Step 3 case or unknown synthetic profile: {record['key']}")
    if record.get("memory") != "memory":
        raise ValueError(f"{key}: expected Step 3 answers based on memory notes")
    if record.get("pool") != "all" or record.get("pool_size") != len(profiles):
        raise ValueError(f"{key}: saved candidate pool does not match the current full profile pool")


def reduce_case(record: dict, profiles: dict[str, Profile], identity: dict | None) -> list[dict]:
    validate_case(record, profiles)
    if identity is not None:
        validate_case(identity, profiles)
        if identity["key"] != record["key"] or set(identity.get("candidates", [])) != set(profiles):
            raise ValueError(f"{record['key']}: saved identification candidates do not match the profile pool")
    total = len(profiles)
    remaining = list(profiles.values())
    target_id = record["profile_id"]
    chosen = identity.get("chosen_profile_id") if identity is not None else None
    rows = []

    def add(stage: str, answer: str, applied: bool) -> None:
        rows.append({
            "profile_id": target_id, "language": record["lang"], "redactor": record["redactor"],
            "k": record["k"], "attribute_model": record["model"],
            "identification_model": identity["model"] if identity is not None else "",
            "stage": stage, "answer": answer, "filter_applied": applied, "initial_count": total,
            "remaining_count": len(remaining), "reduction_pct": 100 * (total - len(remaining)) / total,
            "target_retained": any(candidate.profile_id == target_id for candidate in remaining),
            "step3_identification_available": identity is not None,
            "step3_identification_correct": chosen == target_id if identity is not None else "",
            "attribute_parse_error": bool(record["parse_error"]),
        })

    add("all", "", False)
    for attribute in STAGES:
        answer = record["answers"].get(attribute, INVALID)
        if not isinstance(answer, str):
            raise ValueError(f"{record['key']}: non-string {attribute} answer")
        key = normalize(answer)
        applied = key not in {"", UNKNOWN, INVALID}
        if applied:
            options = {normalize(profile.attribute(attribute)) for profile in profiles.values()}
            if key not in options:
                raise ValueError(f"{record['key']}: {attribute} answer is not a saved pool option")
            remaining = [profile for profile in remaining if normalize(profile.attribute(attribute)) == key]
        add(attribute, answer, applied)
    return rows


def aggregate(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, int, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["redactor"], row["k"], row["stage"])].append(row)
    result = []
    for (redactor, k, stage), members in sorted(groups.items()):
        count = len(members)
        result.append({
            "redactor": redactor, "k": k, "stage": stage, "cases": count,
            "filters_applied": sum(row["filter_applied"] for row in members),
            "mean_candidates": sum(row["remaining_count"] for row in members) / count,
            "mean_reduction_pct": sum(row["reduction_pct"] for row in members) / count,
            "targets_retained": sum(row["target_retained"] for row in members),
            "target_retention_pct": 100 * sum(row["target_retained"] for row in members) / count,
        })
    return result


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"No rows to write to {path}")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def draw_reduction(rows: list[dict], destination: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    lengths = sorted({row["k"] for row in rows})
    redactors = sorted({row["redactor"] for row in rows})
    stages = ("all", *STAGES)
    fig, axes = plt.subplots(2, len(lengths), figsize=(4 * len(lengths), 7), squeeze=False,
                             sharey="row", layout="constrained")
    width = .8 / len(redactors)
    for column, k in enumerate(lengths):
        for index, redactor in enumerate(redactors):
            selected = {row["stage"]: row for row in rows if row["k"] == k and row["redactor"] == redactor}
            if not selected:
                continue
            positions = [position + (index - (len(redactors) - 1) / 2) * width
                         for position in range(len(stages))]
            axes[0, column].bar(positions, [selected[stage]["mean_candidates"] for stage in stages],
                                width=width, label=redactor, color=f"C{index}")
            axes[1, column].bar(positions, [selected[stage]["target_retention_pct"] for stage in stages],
                                width=width, label=redactor, color=f"C{index}")
        axes[0, column].set_title(f"k = {k} notes")
        axes[1, column].set_ylim(0, 105)
        for axis in axes[:, column]:
            axis.set_xticks(range(len(stages)), stages)
            axis.tick_params(axis="x", labelrotation=0)
            axis.grid(axis="y", alpha=.25)
    axes[0, 0].set_ylabel("Mean candidates remaining")
    axes[1, 0].set_ylabel("Target retained (%)")
    axes[0, -1].legend(title="Redactor")
    fig.suptitle("Synthetic search-space reduction and target retention")
    fig.savefig(destination, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redactors", help="comma-separated redactors; default: all saved answers")
    parser.add_argument("--k", type=int, choices=config.MEMORY_LENGTHS, help="one memory length")
    parser.add_argument("--dry-run", action="store_true", help="preview cases without writing or network calls")
    regional = parser.add_mutually_exclusive_group()
    regional.add_argument("--regional-heatmaps", action="store_true",
                          help="generate only offline city-by-occupation heatmaps for the full profile pool")
    regional.add_argument("--regional-maps", action="store_true",
                          help="compare saved attribute guesses with ground truth on offline country maps")
    args = parser.parse_args()

    profiles = load_profiles(config.PROFILES_FILE)
    if args.regional_heatmaps:
        if args.redactors or args.k is not None:
            parser.error("--regional-heatmaps uses the full profile pool; --redactors and --k do not apply")
        print(f"{len(profiles)} synthetic profiles; 0 model calls; no map services.")
        print(f"Output: {OUT / 'regional_heatmaps'}")
        if not args.dry_run:
            from pipeline.regional_heatmaps import write_heatmaps
            write_heatmaps(profiles, OUT / "regional_heatmaps")
        return
    attributes = read_records(config.RESULTS_DIR / "attacks" / "attributes.jsonl")
    wanted = {name.strip() for name in args.redactors.split(",")} if args.redactors else None
    cases = [record for record in attributes.values()
             if (wanted is None or record["redactor"] in wanted) and (args.k is None or record["k"] == args.k)]
    if not cases:
        raise SystemExit("No saved Step 3 attribute answers match the requested filters.")
    if args.regional_maps:
        for record in cases:
            reduce_case(record, profiles, None)
        print(f"{len(profiles)} synthetic profiles; {len(cases)} saved cases; 0 model calls; no map services.")
        print(f"Output: {OUT / 'regional_maps'}")
        if not args.dry_run:
            from pipeline.regional_maps import write_maps
            write_maps(profiles, cases, OUT / "regional_maps")
        return
    identities = read_records(config.RESULTS_DIR / "attacks" / "identify.jsonl", required=False)
    rows = [row for record in cases for row in reduce_case(record, profiles, identities.get(record["key"]))]
    summary = aggregate(rows)
    print(f"{len(profiles)} synthetic candidates; {len(cases)} saved cases; 0 model calls.")
    print(f"Output: {OUT}")
    print("Map lookup sends public city, country and, when needed, public neighborhood names to OpenStreetMap.")
    if args.dry_run:
        return

    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT / "case_stages.csv", rows)
    write_csv(OUT / "stage_summary.csv", summary)
    draw_reduction(summary, OUT / "reduction.png")
    from pipeline.regional_heatmaps import write_heatmaps
    from pipeline.simulation_map import map_candidates

    write_heatmaps(profiles, OUT / "regional_heatmaps")
    mapped, missing = map_candidates(profiles, OUT)
    paired = sum(record["key"] in identities for record in cases)
    models = sorted({record["model"] for record in cases})
    saved_keys = {record["key"] for record in cases}
    coverage = "Current memory directory is unavailable; available-case coverage could not be checked."
    if config.MEMORY_DIR.is_dir():
        available_sets, _ = memory_sets(read_folder(config.MEMORY_DIR), config.MEMORY_LENGTHS)
        available_keys = {
            item.key for item in available_sets
            if item.profile_id in profiles and (wanted is None or item.redactor in wanted)
            and (args.k is None or item.k == args.k)
        }
        coverage = (
            f"Current memory files provide {len(available_keys)} matching cases; "
            f"{len(available_keys - saved_keys)} lack saved attribute answers, and "
            f"{len(saved_keys - available_keys)} saved cases lack current memory sets. "
            "This checks case availability, not whether note contents are unchanged."
        )
    group_counts = [
        row for row in summary if row["stage"] == "all"
    ]
    lines = [
        "# Hypothetical synthetic candidate filtering", "",
        f"- Candidate pool: {len(profiles)} synthetic profiles.",
        f"- Cases: {len(cases)}; cases with saved Step 3 identification: {paired}.",
        f"- Distinct target profiles: {len({record['profile_id'] for record in cases})}.",
        f"- Attribute attacker models: {', '.join(models)}.",
        f"- Mapped profiles by public city center: {mapped}/{len(profiles)}.",
        "- No new model calls were used.",
        "",
        "## What the simulation shows", "",
        "This asks what could happen if the saved Step 3 attribute guesses were used to filter the "
        "same full synthetic profile pool. It is a hypothetical analysis, not a record of how the "
        "Step 3 attacker made its identification decision. It complements Step 4's identification "
        "accuracy by measuring candidate counts and whether the known target remains.",
        "Each case applies the saved location, occupation and education answers in that order. "
        "Unknown or invalid answers leave the pool unchanged. Target identity is used only for "
        "evaluation; if a filter removes the target, it is not restored.",
        "",
        "## Coverage", "",
        coverage,
        "",
        "| Redactor | k notes | Saved cases |",
        "| --- | ---: | ---: |",
        *(f"| {row['redactor']} | {row['k']} | {row['cases']} |" for row in group_counts),
        "",
        "## Weaknesses and interpretation", "",
        "- The pool contains only synthetic profiles; its size and composition do not represent a "
        "real population or establish real-world identification risk.",
        "- Step 3 selected attributes from a fixed set of profile-derived choices. This gives the "
        "attacker information that may not be available in an open-world search.",
        "- Filtering assumes exact matching against known candidate attributes. The selected filter "
        "order is a simulation choice, not a demonstrated optimal search method.",
        "- A smaller pool is not an identification success. The saved Step 3 identification result "
        "comes from a separate attack on the full pool, not an attack on this filtered shortlist.",
        "- Incorrect guesses can exclude the target. Unknown or invalid guesses apply no filter, so "
        "high target retention alone does not demonstrate a successful attack.",
        "- Saved Step 3 records have no note or profile hashes, so their exact historical inputs cannot "
        "be independently verified against the current files.",
        "- Cases from the same profile are related. Group sizes may differ across redactors and k; "
        "small groups are uncertain, and unpaired differences do not establish a causal effect.",
        "- The map shows city-level counts for the original candidate pool, not filtered survivors, "
        "individual locations or journeys.",
        "- Regional city-by-occupation heatmaps show the synthetic pool, not the attributes "
        "an attacker actually learned or real-world identification risk.",
        "",
        "## Rerunning", "",
        "Rerunning Step 5 with unchanged inputs only regenerates these outputs; it does not add cases "
        "or make model calls. A broader experiment requires additional Step 2 memories and Step 3 "
        "answers, followed by Step 4 and Step 5; those earlier model calls may incur costs.",
        "",
        "## Outputs", "",
        "- `case_stages.csv`: individual stage sizes, reductions, target retention and Step 3 outcomes.",
        "- `stage_summary.csv` and `reduction.png`: counts and retention by redactor and k.",
        "- `candidate_map.png` and `candidate_cities.csv`: synthetic profile counts by public city center, "
        "not individual locations.",
        "- `regional_heatmaps/report.md`: offline city-by-occupation grids, counts and limitations.",
        *(["- `regional_maps/report.md`: offline geographic comparisons of saved guesses and ground truth."]
          if (OUT / "regional_maps" / "report.md").exists() else []),
        "",
        "## Unmapped cities", "",
        *(f"- {warning}" for warning in missing),
        *([] if missing else ["- None."]),
    ]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if missing:
        raise SystemExit(f"Analysis saved, but {len(missing)} cities could not be mapped; see {OUT / 'report.md'}.")
    print(f"Done. Results: {OUT}")


if __name__ == "__main__":
    main()
