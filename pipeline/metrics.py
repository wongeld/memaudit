"""Scoring and confidence intervals.

Confidence intervals resample profiles (a profile-level bootstrap), because everything
measured for one profile is related. All intervals are 95%.

Span-level redaction (precision, recall, F1)
    A reference span is found when every letter and digit in it is masked. Spaces and
    punctuation do not need to be masked, so "Juma" and "Barasa" masked separately still
    find "Juma Barasa".
    A mask is correct when it overlaps a reference span.
    precision = correct masks / all masks;  recall = found spans / all reference spans.
    Both are pooled over every session of every profile in a language ("micro" averages).

Attribute recovery and identification
    Accuracy is computed per profile, then averaged over profiles.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

import config

from .attacks import INVALID, UNKNOWN, normalize
from .profiles import ATTRIBUTES, Profile
from .reference import KINDS, RefSpan

NAN = math.nan


# --------------------------------------------------------------------------- #
# Bootstrap
# --------------------------------------------------------------------------- #

def _resample_index(n: int) -> np.ndarray:
    rng = np.random.default_rng(config.SEED)
    return rng.integers(0, n, size=(config.BOOTSTRAP_RESAMPLES, n))


def _interval(samples: np.ndarray) -> tuple[float, float]:
    samples = samples[~np.isnan(samples)]
    if len(samples) == 0:
        return NAN, NAN
    low, high = np.percentile(samples, [2.5, 97.5])
    return float(low), float(high)


def mean_with_ci(values: list[float]) -> tuple[float, float, float]:
    """Mean of one value per profile, with a 95% interval. No interval for fewer than 2 profiles."""
    if not values:
        return NAN, NAN, NAN
    data = np.asarray(values, dtype=float)
    if len(data) < 2:
        return float(data.mean()), NAN, NAN
    return (float(data.mean()), *_interval(data[_resample_index(len(data))].mean(axis=1)))


# --------------------------------------------------------------------------- #
# Span-level redaction
# --------------------------------------------------------------------------- #

def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def match_spans(text: str, reference: list[RefSpan], masks: list[tuple[int, int]],
                ignore: list[tuple[int, int]]) -> dict:
    """Compare one redactor's masks with the reference spans for one session.

    Masks that lie entirely inside an ignored range ([PROFILE_ID]) are not counted.
    """
    masks = [m for m in masks if not any(i0 <= m[0] and m[1] <= i1 for i0, i1 in ignore)]
    masked = np.zeros(len(text) + 1, dtype=bool)
    for start, end in masks:
        masked[start:end] = True

    counts = {"masks": len(masks), "correct_masks": 0, "reference": len(reference), "found": 0, "touched": 0}
    for kind in KINDS:
        counts[f"reference_{kind}"] = 0
        counts[f"found_{kind}"] = 0
    counts["correct_masks"] = sum(1 for m in masks if any(_overlaps(*m, r.start, r.end) for r in reference))
    for r in reference:
        letters = [i for i in range(r.start, r.end) if text[i].isalnum()]
        found = all(masked[i] for i in letters)
        counts["found"] += found
        counts["touched"] += any(masked[r.start:r.end])
        counts[f"reference_{r.kind}"] += 1
        counts[f"found_{r.kind}"] += found
    return counts


def span_scores(per_profile: dict[str, dict]) -> dict:
    """Precision, recall and F1 pooled over profiles, each with a 95% interval.

    `per_profile` maps profile_id to its summed counts from match_spans.
    """
    ids = sorted(per_profile)
    masks = np.array([per_profile[p]["masks"] for p in ids], dtype=float)
    correct = np.array([per_profile[p]["correct_masks"] for p in ids], dtype=float)
    reference = np.array([per_profile[p]["reference"] for p in ids], dtype=float)
    found = np.array([per_profile[p]["found"] for p in ids], dtype=float)

    def scores(m, c, r, f):
        with np.errstate(divide="ignore", invalid="ignore"):
            precision = np.where(m > 0, c / m, np.nan)
            recall = np.where(r > 0, f / r, np.nan)
            f1 = np.where(precision + recall > 0, 2 * precision * recall / (precision + recall), np.nan)
        return precision, recall, f1

    point = scores(masks.sum(), correct.sum(), reference.sum(), found.sum())
    out = {"profiles": len(ids), "reference_spans": int(reference.sum()), "masks": int(masks.sum())}
    if len(ids) >= 2:
        idx = _resample_index(len(ids))
        samples = scores(masks[idx].sum(1), correct[idx].sum(1), reference[idx].sum(1), found[idx].sum(1))
    else:
        samples = (np.array([np.nan]),) * 3
    for name, value, sample in zip(("precision", "recall", "f1"), point, samples, strict=True):
        low, high = _interval(np.asarray(sample, dtype=float)) if len(ids) >= 2 else (NAN, NAN)
        out[name], out[f"{name}_low"], out[f"{name}_high"] = float(value), low, high
    return out


# --------------------------------------------------------------------------- #
# Attribute recovery and identification
# --------------------------------------------------------------------------- #

def attribute_rows(records: list[dict], profiles: dict[str, Profile]) -> list[dict]:
    """One row per (memory set, attribute): the answer, the truth and whether they match."""
    rows = []
    for record in records:
        profile = profiles.get(record["profile_id"])
        if profile is None:
            continue
        for attribute in ATTRIBUTES:
            truth = profile.attribute(attribute)
            answer = record["answers"].get(attribute, INVALID)
            rows.append({
                "profile_id": record["profile_id"], "lang": record["lang"], "redactor": record["redactor"],
                "k": record["k"], "attribute": attribute, "truth": truth, "answer": answer,
                "correct": int(normalize(answer) == normalize(truth)),
                "unknown": int(answer == UNKNOWN), "invalid": int(answer == INVALID),
            })
    return rows


def identification_rows(records: list[dict]) -> list[dict]:
    """One row per identification query. A reply that could not be read counts as wrong."""
    return [{
        "profile_id": r["profile_id"], "lang": r["lang"], "redactor": r["redactor"], "k": r["k"],
        "correct": int(r["chosen_profile_id"] == r["profile_id"]),
        "pool_size": r["pool_size"], "parse_error": int(r["parse_error"]),
    } for r in records]


def group(rows: list[dict], keys: tuple[str, ...]) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in keys)].append(row)
    return dict(groups)


def per_profile(rows: list[dict], value: str) -> dict[str, float]:
    """Mean of a column within each profile."""
    values: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        values[row["profile_id"]].append(float(row[value]))
    return {pid: sum(v) / len(v) for pid, v in values.items()}


def accuracy_table(rows: list[dict], keys: tuple[str, ...], value: str = "correct") -> list[dict]:
    """Per group: number of profiles and the mean of `value` with a 95% interval."""
    out = []
    for key, members in group(rows, keys).items():
        scores = per_profile(members, value)
        mean, low, high = mean_with_ci(list(scores.values()))
        out.append({**dict(zip(keys, key, strict=True)), "profiles": len(scores),
                    "value": mean, "low": low, "high": high})
    return out


def paired_change(rows: list[dict], keys: tuple[str, ...], compare: str, base, value: str = "correct") -> list[dict]:
    """Per profile: value with each other `compare` level minus value at `base`, averaged with a 95% interval.

    Used for the growth from k = 1 to larger k, and for each redactor against no redaction.
    Only profiles that have both levels count.
    """
    out = []
    for key, members in group(rows, keys).items():
        levels = sorted({r[compare] for r in members}, key=str)
        by_level = {lvl: per_profile([r for r in members if r[compare] == lvl], value) for lvl in levels}
        if base not in by_level:
            continue
        for level in levels:
            if level == base:
                continue
            diffs = [by_level[level][p] - by_level[base][p] for p in by_level[level] if p in by_level[base]]
            mean, low, high = mean_with_ci(diffs)
            out.append({**dict(zip(keys, key, strict=True)), "from": base, "to": level,
                        "profiles": len(diffs), "value": mean, "low": low, "high": high})
    return out


def baselines(profiles: dict[str, Profile], options: dict[str, list[str]], lang: str) -> dict[str, float]:
    """What guessing would score on one language's profiles, averaged over the six attributes.

    random:   picking an option at random.
    majority: always picking the most common true value among that language's profiles.
    """
    targets = [p for p in profiles.values() if p.language == lang]
    random_scores, majority_scores = [], []
    for attribute in ATTRIBUTES:
        values = [normalize(p.attribute(attribute)) for p in targets]
        random_scores.append(1 / len(options[attribute]))
        majority_scores.append(max(values.count(v) for v in set(values)) / len(values))
    return {"random": sum(random_scores) / len(ATTRIBUTES), "majority": sum(majority_scores) / len(ATTRIBUTES)}
