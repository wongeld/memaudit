"""Step 4: score everything and write the results.

    python step4_evaluate.py

Reads   sessions/, profiles/profiles.csv, redacted/, results/attacks/
Writes  results/paper_tables.md   Tables 1-3 of the paper, filled in
        results/report.md         every result with 95% confidence intervals and explanations
        results/tables/*.csv      the same numbers for spreadsheets
        results/figures/*.png     accuracy against number of sessions
The paper tables are also printed in the terminal.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime

from rich.console import Console
from rich.table import Table

import config
from pipeline.attacks import attribute_options, candidate_pool
from pipeline.metrics import (
    accuracy_table,
    attribute_rows,
    baselines,
    identification_rows,
    match_spans,
    paired_change,
    span_scores,
)
from pipeline.profiles import ATTRIBUTE_NAMES, ATTRIBUTES, load_profiles, lookalikes
from pipeline.reference import KINDS, reference_spans
from pipeline.sessions import PROFILE_ID_MASK, load_sessions

console = Console()
LANGS = ("en", "sw", "am")
REDACTOR_ORDER = ("none", "presidio", "ner", "gemini", "open")
OUT = config.RESULTS_DIR

# Line names in the figures (one legend serves all three languages).
LEGEND = {"none": "No redaction", "presidio": "Presidio", "ner": "NER / MasakhaNER",
          "gemini": "LLM (Gemini)", "open": "LLM (open-weight)"}


def approach(redactor: str, lang: str) -> str:
    """Row names used in the paper."""
    return {
        "none": "No redaction",
        "presidio": "Presidio based redactor",
        "ner": "NER based redactor" if lang == "en" else "MasakhaNER based redactor",
        "gemini": "LLM Data Anonymization",
        "open": "LLM Data Anonymization (open-weight)",
    }.get(redactor, redactor)


def rank(redactor: str) -> int:
    return REDACTOR_ORDER.index(redactor) if redactor in REDACTOR_ORDER else len(REDACTOR_ORDER)


def pct(v: float) -> str:
    return "n/a" if v is None or math.isnan(v) else f"{100 * v:.1f}%"


def dec(v: float) -> str:
    return "n/a" if v is None or math.isnan(v) else f"{v:.2f}"


def ci(v: float, low: float, high: float, fmt=pct) -> str:
    if math.isnan(v):
        return "n/a"
    return fmt(v) if math.isnan(low) else f"{fmt(v)} [{fmt(low)}, {fmt(high)}]"


def signed(row: dict) -> str:
    def p(x: float) -> str:
        return f"{100 * x:+.1f}"
    if math.isnan(row["value"]):
        return "n/a"
    base = f"{p(row['value'])} pts"
    return base if math.isnan(row["low"]) else f"{base} [{p(row['low'])}, {p(row['high'])}]"


def md_table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def show(title: str, headers: list[str], rows: list[list]) -> None:
    table = Table(title=title, title_justify="left", title_style="bold")
    for h in headers:
        table.add_column(h)
    for row in rows:
        table.add_row(*[str(c) for c in row])
    console.print(table)


def write_csv(name: str, rows: list[dict]) -> None:
    path = OUT / "tables" / f"{name}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: round(v, 4) if isinstance(v, float) else v for k, v in row.items()})


def read_jsonl(name: str) -> list[dict]:
    path = OUT / "attacks" / f"{name}.jsonl"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def figure(name: str, title: str, table: list[dict], chance: dict[str, float] | None = None) -> str | None:
    """Accuracy against k: one panel per language, one line per redactor, 95% interval bars."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    langs = [lang for lang in LANGS if any(r["lang"] == lang for r in table)]
    if not langs:
        return None
    fig, axes = plt.subplots(1, len(langs), figsize=(4.3 * len(langs), 3.7), sharey=True, squeeze=False)
    for ax, lang in zip(axes[0], langs, strict=True):
        rows = [r for r in table if r["lang"] == lang]
        ks = sorted({r["k"] for r in rows})
        redactors = sorted({r["redactor"] for r in rows}, key=rank)
        for i, redactor in enumerate(redactors):
            # Lines are shifted slightly sideways so equal values do not hide each other.
            shift = (i - (len(redactors) - 1) / 2) * 0.06
            pts = sorted((r for r in rows if r["redactor"] == redactor), key=lambda r: r["k"])
            low = [0 if math.isnan(r["low"]) else r["value"] - r["low"] for r in pts]
            high = [0 if math.isnan(r["high"]) else r["high"] - r["value"] for r in pts]
            ax.errorbar([ks.index(r["k"]) + shift for r in pts], [r["value"] for r in pts], yerr=[low, high],
                        marker="o", capsize=3, label=LEGEND.get(redactor, redactor))
        if chance and lang in chance:
            ax.axhline(chance[lang], color="grey", linestyle="--", linewidth=1, label="chance")
        ax.set_title(config.LANGUAGE_NAMES[lang])
        ax.set_xticks(range(len(ks)), [str(k) for k in ks])
        ax.set_xlim(-0.4, len(ks) - 0.6)
        ax.set_ylim(0, 1.05)
        ax.set_xlabel("sessions in memory (k)")
        ax.grid(alpha=0.3)
    axes[0][0].set_ylabel("accuracy")
    axes[0][-1].legend(fontsize=7, loc="lower right")
    fig.suptitle(title)
    fig.tight_layout()
    path = OUT / "figures" / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return f"figures/{name}.png"


# --------------------------------------------------------------------------- #

def redaction_results(profiles, all_sessions) -> tuple[list[dict], list[dict], list[str]]:
    """Span-level precision, recall and F1 per language and redactor (Table 1)."""
    counts: dict[tuple[str, str], dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    problems = []
    for pid, sessions in all_sessions.items():
        if pid not in profiles:
            continue
        profile = profiles[pid]
        for session in sessions:
            text = session.transcript()
            original = config.REDACTED_DIR / f"{session.stem}_none.txt"
            if original.exists() and original.read_text(encoding="utf-8") != text:
                problems.append(f"{session.stem}: redacted/ was made with different session settings; "
                                "rerun step1_redact.py --force")
                continue
            reference = reference_spans(text, profile, session)
            ignore = [(i, i + len(PROFILE_ID_MASK)) for i in range(len(text))
                      if text.startswith(PROFILE_ID_MASK, i)]
            for path in config.REDACTED_DIR.glob(f"{session.stem}_*.spans.json"):
                redactor = path.name[len(session.stem) + 1:-len(".spans.json")]
                if redactor == "none":
                    continue
                masks = [(s["start"], s["end"]) for s in json.loads(path.read_text(encoding="utf-8"))]
                counts[(profile.language, redactor)][pid].update(match_spans(text, reference, masks, ignore))

    table, by_kind = [], []
    for (lang, redactor), per_profile in counts.items():
        table.append({"lang": lang, "redactor": redactor, **span_scores(per_profile)})
        total = sum(per_profile.values(), Counter())
        for kind in KINDS:
            if total[f"reference_{kind}"]:
                by_kind.append({"lang": lang, "redactor": redactor, "kind": kind,
                                "reference_spans": total[f"reference_{kind}"],
                                "recall": total[f"found_{kind}"] / total[f"reference_{kind}"]})
    def order(row: dict) -> tuple:
        return LANGS.index(row["lang"]), rank(row["redactor"]), row.get("kind", "")

    return sorted(table, key=order), sorted(by_kind, key=order), problems


def main() -> None:
    profiles = load_profiles()
    all_sessions = load_sessions()
    attr_records, id_records = read_jsonl("attributes"), read_jsonl("identify")
    report: list[str] = []
    paper: list[str] = []

    def models(records: list[dict]) -> str:
        return ", ".join(sorted({r["model"] for r in records})) or "not run yet"

    memory_source = {r.get("memory") for r in attr_records + id_records}
    stand_in = "redacted" in memory_source
    redactor_models = {}
    models_file = config.REDACTED_DIR / "models.json"
    if models_file.exists():
        redactor_models = json.loads(models_file.read_text(encoding="utf-8"))
    summarizer_file = config.MEMORY_DIR / "models.json"
    summarizer = json.loads(summarizer_file.read_text(encoding="utf-8")).get("summarizer", "-") \
        if summarizer_file.exists() else "-"

    header = [
        f"Generated {datetime.now():%Y-%m-%d %H:%M}.",
        f"Sessions: {config.SESSION_SIZE or 'one per self-introduction'} user messages each. "
        f"Gemini redactor: {redactor_models.get('gemini', '-')}. Summarizer: {summarizer}. "
        f"Attacker: {models(attr_records + id_records)}. Candidate pool: {config.CANDIDATE_POOL}.",
    ]
    if stand_in:
        header.append("**Warning: the attacks read the redacted sessions instead of memory notes. "
                      "This tests the pipeline; it is not the study.**")

    # ---------------------------------------------------------------- data overview
    complete = {pid: [s for s in ss if s.complete] for pid, ss in all_sessions.items() if pid in profiles}
    overview = []
    for lang in LANGS:
        ids = [p for p in profiles.values() if p.language == lang]
        with_sessions = [p for p in ids if complete.get(p.profile_id)]
        counts = [len(complete[p.profile_id]) for p in with_sessions]
        overview.append([config.LANGUAGE_NAMES[lang], len(ids), len(with_sessions),
                         f"{min(counts)}-{max(counts)}" if counts else "-", sum(counts)])
    look = lookalikes(profiles)
    twins = [r for r in look if r["same_all_six_attributes"]]
    report += ["# Results", "", *header, "",
               "## Data", "",
               md_table(["Language", "Profiles", "Profiles with sessions", "Sessions per profile", "Sessions"],
                        overview), "",
               f"Profiles were built to overlap: {sum(1 for r in look if r['same_location_occupation_education'])} "
               f"of {len(look)} share their location, occupation and education with another profile, and "
               f"{len(twins)} share all six attributes with another profile "
               f"({', '.join(r['name'] for r in twins) or 'none'}). Such twins can only be told apart by "
               "direct identifiers that survive redaction. Details: `tables/lookalikes.csv`.", ""]
    write_csv("lookalikes", look)

    # ---------------------------------------------------------------- Table 1
    spans, by_kind, problems = redaction_results(profiles, all_sessions)
    write_csv("redaction_spans", spans)
    write_csv("redaction_recall_by_kind", by_kind)
    t1_rows, t1_full = [], []
    for lang in LANGS:
        for redactor in ("presidio", "ner", "gemini", "open"):
            row = next((r for r in spans if r["lang"] == lang and r["redactor"] == redactor), None)
            if row is None and redactor == "open":
                continue
            name = approach(redactor, lang)
            if row is None:
                t1_rows.append([config.LANGUAGE_NAMES[lang], name, "n/a", "n/a", "n/a"])
                continue
            t1_rows.append([config.LANGUAGE_NAMES[lang], name, dec(row["precision"]), dec(row["recall"]),
                            dec(row["f1"])])
            t1_full.append([config.LANGUAGE_NAMES[lang], name, row["profiles"], row["reference_spans"],
                            row["masks"], ci(row["precision"], row["precision_low"], row["precision_high"], dec),
                            ci(row["recall"], row["recall_low"], row["recall_high"], dec),
                            ci(row["f1"], row["f1_low"], row["f1_high"], dec)])
    t1_headers = ["Language", "Redaction Approach", "Precision", "Recall", "F1 Score"]
    span_note = ("Reference spans are the profile's name, phone, email, national ID, city, country and "
                 "neighbourhood, plus places the user searched for and coordinates the user gave, wherever "
                 "they appear in the session. They are found automatically from profiles.csv and the user's "
                 "messages, not annotated by hand. A span counts as found only if all its letters and digits "
                 "are masked; a mask counts as correct if it overlaps a reference span.")
    paper += ["# Tables for the paper", "", *header, "",
              "## Table 1. Span-level redaction outcomes by language and method", "",
              md_table(t1_headers, t1_rows), "", span_note, ""]
    report += ["## 1. Span-level redaction (Table 1)", "", span_note, "",
               md_table(["Language", "Approach", "Profiles", "Reference spans", "Masks",
                         "Precision [95% CI]", "Recall [95% CI]", "F1 [95% CI]"], t1_full), ""]
    if by_kind:
        kinds_present = [k for k in KINDS if any(r["kind"] == k for r in by_kind)]
        rows = []
        for lang in LANGS:
            for redactor in ("presidio", "ner", "gemini", "open"):
                cells = {r["kind"]: r for r in by_kind if r["lang"] == lang and r["redactor"] == redactor}
                if cells:
                    rows.append([config.LANGUAGE_NAMES[lang], approach(redactor, lang)]
                                + [pct(cells[k]["recall"]) if k in cells else "-" for k in kinds_present])
        report += ["Recall by kind of identifier (share of reference spans fully masked):", "",
                   md_table(["Language", "Approach"] + [k.replace("_", " ").title() for k in kinds_present],
                            rows), ""]
    if problems:
        report += [f"**{len(problems)} sessions were skipped** because redacted/ does not match the current "
                   "session settings. Rerun `python step1_redact.py --force`.", ""]

    # ---------------------------------------------------------------- Table 2
    attr = attribute_rows(attr_records, profiles)
    attr_table = accuracy_table(attr, ("lang", "redactor", "k"))
    write_csv("attribute_recovery", attr_table)
    write_csv("attribute_recovery_by_attribute", accuracy_table(attr, ("lang", "redactor", "k", "attribute")))
    unknown = {(r["lang"], r["redactor"], r["k"]): r["value"]
               for r in accuracy_table(attr, ("lang", "redactor", "k"), "unknown")}
    ks = config.MEMORY_LENGTHS

    def cell(table: list[dict], lang: str, redactor: str, k: int) -> dict | None:
        return next((r for r in table if (r["lang"], r["redactor"], r["k"]) == (lang, redactor, k)), None)

    def k_header() -> list[str]:
        return [f"{k} Session" + ("s" if k > 1 else "") for k in ks]

    def k_row(table, lang, redactor):
        return [pct(c["value"]) if (c := cell(table, lang, redactor, k)) else "n/a" for k in ks]

    def n_note(table) -> str:
        """How many profiles each cell averages, e.g. "1 session: English 20, Swahili 10, Amharic 10"."""
        ns: dict[int, dict[str, int]] = defaultdict(dict)
        for r in table:
            ns[r["k"]][r["lang"]] = max(ns[r["k"]].get(r["lang"], 0), r["profiles"])
        parts = []
        for k, by_lang in sorted(ns.items()):
            counts = ", ".join(f"{config.LANGUAGE_NAMES[lang]} {by_lang[lang]}" for lang in LANGS if lang in by_lang)
            parts.append(f"{k} session{'s' if k > 1 else ''}: {counts}")
        return "; ".join(parts)

    t2 = [["English", "No redaction"] + k_row(attr_table, "en", "none")]
    t2 += [[config.LANGUAGE_NAMES[lang], "Presidio based redactor"] + k_row(attr_table, lang, "presidio")
           for lang in LANGS]
    t2_note = ("Share of the six attributes (age group, location, occupation, education, family status, "
               "health condition) the attacker got right from the first k memory notes, averaged over "
               "profiles. \"Unknown\" counts as wrong. n/a: no profile has that many sessions yet."
               + (f" Profiles per cell: {n_note(attr_table)}." if attr_table else ""))
    paper += ["## Table 2. Attribute recovery accuracy across session lengths", "",
              md_table(["Language", "Redaction Approach"] + k_header(), t2), "", t2_note, ""]

    options_all = attribute_options(list(profiles.values()))
    base_rows = []
    for lang in LANGS:
        pool = candidate_pool(next(p for p in profiles.values() if p.language == lang), profiles)
        b = baselines(profiles, attribute_options(pool) if config.CANDIDATE_POOL == "language" else options_all,
                      lang)
        base_rows.append([config.LANGUAGE_NAMES[lang], pct(b["random"]), pct(b["majority"])])
    report += ["## 2. Attribute recovery (Table 2)", "", t2_note, ""]
    if attr_table:
        full = [[config.LANGUAGE_NAMES[r["lang"]], approach(r["redactor"], r["lang"]), r["k"], r["profiles"],
                 ci(r["value"], r["low"], r["high"]), pct(unknown[(r["lang"], r["redactor"], r["k"])])]
                for r in sorted(attr_table, key=lambda r: (LANGS.index(r["lang"]), rank(r["redactor"]), r["k"]))]
        report += [md_table(["Language", "Approach", "k", "Profiles", "Accuracy [95% CI]", "Answered unknown"],
                            full), ""]
        per_attr = accuracy_table(attr, ("lang", "redactor", "attribute"))
        rows = []
        for lang in LANGS:
            for redactor in sorted({r["redactor"] for r in per_attr if r["lang"] == lang}, key=rank):
                cells = {r["attribute"]: r["value"] for r in per_attr if (r["lang"], r["redactor"]) == (lang, redactor)}
                rows.append([config.LANGUAGE_NAMES[lang], approach(redactor, lang)]
                            + [pct(cells.get(a, math.nan)) for a in ATTRIBUTES])
        report += ["Accuracy by attribute (all k together):", "",
                   md_table(["Language", "Approach"] + [ATTRIBUTE_NAMES[a] for a in ATTRIBUTES], rows), ""]
        if path := figure("attribute_recovery", "Attribute recovery", attr_table):
            report += [f"![Attribute recovery]({path})", ""]
    report += ["What guessing would score (average over the six attributes):", "",
               md_table(["Language", "Random option", "Most common value"], base_rows), ""]

    # ---------------------------------------------------------------- Table 3
    ident = identification_rows(id_records)
    id_table = accuracy_table(ident, ("lang", "redactor", "k"))
    write_csv("identification", id_table)
    chance = {r["lang"]: 1 / r["pool_size"] for r in ident}
    pool_sizes = sorted({r["pool_size"] for r in ident})
    chance_text = (f"Random chance: {pct(1 / pool_sizes[0])} (1 of {pool_sizes[0]} candidates)."
                   if len(pool_sizes) == 1 else
                   "Random chance: " + ", ".join(f"{config.LANGUAGE_NAMES[lang]} {pct(c)}"
                                                 for lang, c in sorted(chance.items())) + ".")
    t3 = [[config.LANGUAGE_NAMES[lang], "Presidio based redactor"] + k_row(id_table, lang, "presidio")
          for lang in LANGS]
    t3_note = ("Share of memory sets the attacker matched to the right profile out of the candidate list, "
               "averaged over profiles. " + (chance_text if ident else "")
               + (f" Profiles per cell: {n_note(id_table)}." if id_table else ""))
    paper += ["## Table 3. Profile re-identification accuracy", "",
              md_table(["Language", "Redaction Approach"] + k_header(), t3), "", t3_note, ""]
    report += ["## 3. Profile identification (Table 3)", "", t3_note, ""]
    if id_table:
        full = [[config.LANGUAGE_NAMES[r["lang"]], approach(r["redactor"], r["lang"]), r["k"], r["profiles"],
                 ci(r["value"], r["low"], r["high"])]
                for r in sorted(id_table, key=lambda r: (LANGS.index(r["lang"]), rank(r["redactor"]), r["k"]))]
        report += [md_table(["Language", "Approach", "k", "Profiles", "Accuracy [95% CI]"], full), ""]
        errors = sum(r["parse_error"] for r in ident)
        if errors:
            report += [f"{errors} replies could not be read and were counted as wrong.", ""]
        if path := figure("identification", "Profile identification", id_table, chance):
            report += [f"![Profile identification]({path})", ""]

    # ---------------------------------------------------------------- growth and redaction effect
    for title, rows in (("attribute recovery", attr), ("identification", ident)):
        if not rows:
            continue
        growth = paired_change(rows, ("lang", "redactor"), "k", min(r["k"] for r in rows))
        effect = paired_change(rows, ("lang", "k"), "redactor", "none")
        write_csv(f"{title.replace(' ', '_')}_growth", growth)
        write_csv(f"{title.replace(' ', '_')}_vs_no_redaction", effect)
        if growth:
            report += [f"## Does {title} grow as memory accumulates?", "",
                       "Change per profile from 1 session to k sessions, in percentage points.", "",
                       md_table(["Language", "Approach", "From k", "To k", "Profiles", "Change [95% CI]"],
                                [[config.LANGUAGE_NAMES[r["lang"]], approach(r["redactor"], r["lang"]),
                                  r["from"], r["to"], r["profiles"], signed(r)]
                                 for r in sorted(growth, key=lambda r: (LANGS.index(r["lang"]), rank(r["redactor"]),
                                                                        r["to"]))]), ""]
        if effect:
            report += [f"## How much does each redactor reduce {title}?", "",
                       "Accuracy with the redactor minus accuracy with no redaction, per profile, same language "
                       "and k (negative = redaction helped).", "",
                       md_table(["Language", "k", "Approach", "Profiles", "Change vs no redaction [95% CI]"],
                                [[config.LANGUAGE_NAMES[r["lang"]], r["k"], approach(r["to"], r["lang"]),
                                  r["profiles"], signed(r)]
                                 for r in sorted(effect, key=lambda r: (LANGS.index(r["lang"]), r["k"],
                                                                        rank(r["to"])))]), ""]

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "paper_tables.md").write_text("\n".join(paper), encoding="utf-8")
    (OUT / "report.md").write_text("\n".join(report), encoding="utf-8")

    show("Table 1. Span-level redaction outcomes", t1_headers, t1_rows)
    show("Table 2. Attribute recovery accuracy", ["Language", "Approach"] + k_header(), t2)
    show("Table 3. Profile re-identification accuracy", ["Language", "Approach"] + k_header(), t3)
    if ident:
        console.print(chance_text)
    if stand_in:
        console.print("[yellow]The attacks read redacted sessions, not memory notes: pipeline test only.[/]")
    if problems:
        console.print(f"[yellow]{len(problems)} sessions skipped: rerun step1_redact.py --force.[/]")
    console.print("\nWrote results/paper_tables.md, results/report.md, results/tables/ and results/figures/.")


if __name__ == "__main__":
    main()
