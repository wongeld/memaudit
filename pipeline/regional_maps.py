"""Compare saved city and occupation guesses with synthetic ground truth."""

from __future__ import annotations

import csv
import json
import math
import re
import textwrap
from collections import Counter, defaultdict
from pathlib import Path
from typing import TypedDict

import config
from pipeline.attacks import INVALID, UNKNOWN, normalize
from pipeline.profiles import Profile
from pipeline.regional_heatmaps import regional_counts

GEODATA = config.ROOT / "pipeline" / "geodata" / "natural_earth_regions.geojson"


class GuessRow(TypedDict):
    country: str
    city: str
    occupation: str
    candidates: int | None
    cases: int
    correct_cases: int | None


def guess_counts(profiles: dict[str, Profile], cases: list[dict]) -> tuple[list[GuessRow], int, int]:
    locations: dict[str, tuple[str, str]] = {}
    occupations: dict[str, str] = {}
    for profile in profiles.values():
        key = normalize(profile.location)
        place = (profile.country, profile.city)
        if key in locations and locations[key] != place:
            raise ValueError(f"Location {profile.location!r} maps to multiple cities or countries.")
        locations[key] = place
        occupations.setdefault(normalize(profile.occupation), profile.occupation)

    pool_counts = {
        (normalize(row["country"]), normalize(row["city"]), normalize(row["occupation"])): row["count"]
        for row in regional_counts(profiles)
    }
    counts: Counter[tuple[str, str, str]] = Counter()
    correct_counts: Counter[tuple[str, str, str]] = Counter()
    unknown_location = 0
    unknown_occupation = 0
    for case in cases:
        answers = case["answers"]
        location, occupation = (normalize(answers.get(name, INVALID))
                                for name in ("location", "occupation"))
        if occupation in ("", UNKNOWN, INVALID):
            unknown_occupation += 1
            occupation = ""
        elif occupation not in occupations:
            raise ValueError(f"{case['key']}: occupation is not a profile-pool option")
        if location in ("", UNKNOWN, INVALID):
            unknown_location += 1
            continue
        if location not in locations:
            raise ValueError(f"{case['key']}: location is not a profile-pool option")
        country, city = locations[location]
        counts[(country, city, occupation)] += 1
        target = profiles[case["profile_id"]]
        if occupation and location == normalize(target.location) and occupation == normalize(target.occupation):
            correct_counts[(country, city, occupation)] += 1

    rows: list[GuessRow] = []
    for (country, city, occupation), count in sorted(counts.items()):
        candidates = pool_counts.get((normalize(country), normalize(city), occupation), 0)
        rows.append({"country": country, "city": city,
                     "occupation": occupations[occupation] if occupation else "Unknown occupation",
                     "candidates": candidates if occupation else None, "cases": count,
                     "correct_cases": correct_counts[(country, city, occupation)] if occupation else None})
    return rows, unknown_location, unknown_occupation


def load_geodata(profiles: dict[str, Profile]) -> tuple[dict[str, dict], dict[tuple[str, str], tuple[float, float]]]:
    with GEODATA.open(encoding="utf-8") as stream:
        data = json.load(stream)
    countries = {}
    cities = {}
    for feature in data["features"]:
        props = feature["properties"]
        if props["kind"] == "country":
            countries[normalize(props["name"])] = feature["geometry"]
        elif props["kind"] == "city":
            cities[(normalize(props["country"]), normalize(props["name"]))] = tuple(
                feature["geometry"]["coordinates"]
            )
    for profile in profiles.values():
        country = normalize(profile.country)
        if country not in countries or (country, normalize(profile.city)) not in cities:
            raise ValueError(f"No Natural Earth geometry for {profile.city}, {profile.country}; "
                             "update the offline geographic data before plotting.")
    return countries, cities


def _draw_country(axis, geometry: dict, points: list[tuple[float, float]]) -> bool:
    from matplotlib.patches import Polygon

    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    for polygon in polygons:
        axis.add_patch(Polygon(polygon[0], closed=True, facecolor="#e8ece8",
                               edgecolor="#586a60", linewidth=1))
    vertices = [point for polygon in polygons for point in polygon[0]]
    min_x, max_x = min(p[0] for p in vertices), max(p[0] for p in vertices)
    min_y, max_y = min(p[1] for p in vertices), max(p[1] for p in vertices)
    contiguous = (min_x < -150 and max_x < -60 and min_y < 25 and max_y > 60
                  and all(-127 <= x <= -65 and 23 <= y <= 51 for x, y in points))
    if contiguous:
        min_x, max_x, min_y, max_y = -127, -65, 23, 51
    margin_x = (max_x - min_x) * .06
    margin_y = (max_y - min_y) * .06
    axis.set_xlim(min_x - margin_x, max_x + margin_x)
    axis.set_ylim(min_y - margin_y, max_y + margin_y)
    axis.set_aspect(1 / math.cos(math.radians((min_y + max_y) / 2)))
    axis.set_facecolor("#e8f3f7")
    axis.set_xticks([])
    axis.set_yticks([])
    return contiguous


def _marker_color(values: list[int | None]) -> str:
    positive = [value for value in values if value is not None and value > 0]
    if not positive:
        return "#838b92"
    smallest = min(positive)
    return "#d65f5f" if smallest == 1 else "#efb84c" if smallest < 5 else "#69a99b"


def _draw_panel(axis, table, geometry: dict, coordinates: dict[str, tuple[float, float]],
                city_numbers: dict[str, int], entries: list[tuple[str, str, int | None, int, int | None]],
                *, guessed: bool) -> bool:
    grouped: dict[str, list[tuple[str, int | None, int, int | None]]] = defaultdict(list)
    for city, occupation, candidates, cases, correct in entries:
        grouped[city].append((occupation, candidates, cases, correct))
    contiguous = _draw_country(axis, geometry, list(coordinates.values()))
    for city, items in grouped.items():
        x, y = coordinates[city]
        axis.scatter([x], [y], s=260, c=[_marker_color([item[1] for item in items])],
                     edgecolors="white", linewidths=1.5, zorder=3)
        axis.text(x, y, str(city_numbers[city]), ha="center", va="center", fontsize=8,
                  fontweight="bold", zorder=4)
    table.axis("off")
    lines = []
    for city in sorted(grouped, key=normalize):
        lines.append(f"{city_numbers[city]}. {city}")
        for occupation, candidates, cases, correct in sorted(grouped[city]):
            count = "unknown" if candidates is None else str(candidates)
            suffix = f"{count} pool matches"
            if guessed:
                suffix += f"; {cases} saved {'case' if cases == 1 else 'cases'}"
                if correct is not None:
                    suffix += f", {correct} correct"
            lines.extend(textwrap.wrap(f"   {occupation}: {suffix}", width=90,
                                       subsequent_indent="      ", replace_whitespace=False))
    if not lines:
        lines = ["No saved cases with a known city in this country."]
    table.text(0, 1, "\n".join(lines), va="top", fontsize=10, linespacing=1.15,
               transform=table.transAxes)
    return contiguous


def draw_comparison(country: str, redactor: str, k: int, total_cases: int, unknown_location: int,
                    pool_size: int, geometry: dict, coordinates: dict[str, tuple[float, float]],
                    truth: list[tuple[str, str, int | None, int, int | None]],
                    guesses: list[tuple[str, str, int | None, int, int | None]], destination: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    city_numbers = {city: index for index, city in enumerate(sorted(coordinates, key=normalize), 1)}
    table_height = max(1.2, .22 * max(len(truth) + len({item[0] for item in truth}),
                                       len(guesses) + len({item[0] for item in guesses})))
    fig, axes = plt.subplots(2, 2, figsize=(16, 6.3 + table_height),
                             gridspec_kw={"height_ratios": [5, table_height]}, layout="constrained")
    left_contiguous = _draw_panel(axes[0, 0], axes[1, 0], geometry, coordinates, city_numbers,
                                  guesses, guessed=True)
    _draw_panel(axes[0, 1], axes[1, 1], geometry, coordinates, city_numbers, truth, guessed=False)
    axes[0, 0].set_title(f"Saved attribute guesses: {sum(item[3] for item in guesses)} cases in this country")
    axes[0, 1].set_title(f"Ground truth: {sum(item[2] or 0 for item in truth)} synthetic profiles")
    view = " (contiguous area only)" if left_contiguous else ""
    fig.suptitle(f"{country}{view} | redactor: {redactor} | k={k}\n"
                 f"Guesses: {total_cases} cases, {unknown_location} with unknown/invalid city | "
                 f"Ground truth: all {pool_size} profiles")
    fig.legend(handles=[Patch(facecolor=color, label=label) for color, label in (
        ("#d65f5f", "1 pool match"), ("#efb84c", "2-4 matches"),
        ("#69a99b", "5+ matches"), ("#838b92", "No positive match / unknown occupation"))],
        loc="outside lower center", ncols=4, frameon=False,
        title="Marker number identifies the city; color shows its smallest positive pool match count")
    fig.savefig(destination, dpi=160)
    plt.close(fig)


def write_maps(profiles: dict[str, Profile], cases: list[dict], destination: Path) -> None:
    if not cases:
        raise ValueError("No saved Step 3 cases to map.")
    geometries, cities = load_geodata(profiles)
    truth = [row for row in regional_counts(profiles) if row["count"]]
    countries = sorted({row["country"] for row in truth}, key=normalize)
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for case in cases:
        groups[(case["redactor"], case["k"])].append(case)
    destination.mkdir(parents=True, exist_ok=True)
    index = []
    output_rows = []
    coverage = []
    filenames: set[str] = set()
    for (redactor, k), records in sorted(groups.items()):
        if len({record["profile_id"] for record in records}) != len(records):
            raise ValueError(f"Duplicate profile cases for {redactor}, k={k}")
        guesses, unknown_location, unknown_occupation = guess_counts(profiles, records)
        coverage.append({"redactor": redactor, "k": k, "saved_cases": len(records),
                         "pool_profiles": len(profiles), "unknown_location": unknown_location,
                         "unknown_occupation": unknown_occupation})
        index.append(f"### {redactor}, k={k} ({len(records)} saved cases; "
                     f"{unknown_location} with unknown/invalid location)")
        index.append("")
        for country in countries:
            country_truth = [row for row in truth if row["country"] == country]
            country_guesses = [row for row in guesses if row["country"] == country]
            coords = {row["city"]: cities[(normalize(country), normalize(row["city"]))]
                      for row in country_truth}
            truth_entries = [(row["city"], row["occupation"], row["count"], 0, None)
                             for row in country_truth]
            guess_entries = [(row["city"], row["occupation"], row["candidates"], row["cases"],
                              row["correct_cases"])
                             for row in country_guesses]
            redactor_slug = re.sub(r"[^a-z0-9]+", "-", redactor.casefold()).strip("-")
            country_slug = re.sub(r"[^a-z0-9]+", "-", country.casefold()).strip("-")
            filename = f"map_{redactor_slug}_k{k}_{country_slug}.png"
            if filename in filenames:
                raise ValueError(f"Map filename collision: {filename}")
            filenames.add(filename)
            draw_comparison(country, redactor, k, len(records), unknown_location, len(profiles),
                            geometries[normalize(country)], coords, truth_entries, guess_entries,
                            destination / filename)
            index.append(f"- [{country}]({filename})")
            for side, entries in (("saved_guesses", guess_entries), ("ground_truth", truth_entries)):
                for city, occupation, candidates, count, correct in entries:
                    output_rows.append({"redactor": redactor, "k": k, "side": side, "country": country,
                                        "city": city, "occupation": occupation, "pool_matches": candidates,
                                        "saved_cases": count if side == "saved_guesses" else "",
                                        "correct_cases": correct if correct is not None else ""})
        index.append("")

    for filename, rows in (("map_counts.csv", output_rows), ("coverage.csv", coverage)):
        with (destination / filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    lines = [
        "# Regional synthetic privacy maps", "",
        f"Each figure compares saved Step 3 city and occupation guesses (left) with all "
        f"{len(profiles)} synthetic profiles (right). The sides do not have the same coverage: "
        "each experiment has only its saved cases, and cases with unknown or invalid locations "
        "cannot be placed. `coverage.csv` records the numbers for each experiment.", "",
        "For each guessed city and occupation, the left panel counts matches in the complete "
        "synthetic pool, the saved cases making that guess, and how many of those cases guessed "
        "both attributes correctly for their target profile. A zero pool count means the combination "
        "matches no synthetic profile. Unknown occupations are shown without a match count. "
        "The right panel shows the actual city-and-occupation counts from the full pool. "
        "`map_counts.csv` contains the displayed counts.", "",
        "A red marker means at least one displayed combination has exactly one match in this "
        "synthetic pool; orange means the smallest positive match count is 2-4, and teal means "
        "5 or more. Gray indicates no positive match or an unknown occupation. A marker summarizes "
        "a city; use the per-city lists for each occupation and for zero-match combinations.", "",
        "These counts assume access to the full synthetic pool and are not an observed "
        "identification, evidence that the guesses are correct, or a real-world risk estimate. "
        "Step 3 chose attributes from profile-derived options. Historical inputs lack hashes. "
        "Some city names are ambiguous; Natural Earth provides a representative city position, "
        "not proof that it is the intended city. Points are city centers, not individual locations.", "",
        "The United States panels show only the contiguous area; all current US synthetic cities "
        "are in that area. The comparison uses offline Natural Earth 1:110m country boundaries "
        "and 1:10m populated-place coordinates, not OpenStreetMap or map tiles. The included "
        "data is extracted from Natural Earth's [country boundaries]"
        "(https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson) "
        "and [populated places]"
        "(https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_10m_populated_places.geojson). "
        "Hawassa and "
        "Mekelle correspond to the Natural Earth names Awasa and Mekele. Natural Earth data is "
        "[public domain](https://www.naturalearthdata.com/about/terms-of-use/).", "",
        "## Maps", "", *index,
    ]
    (destination / "report.md").write_text("\n".join(lines), encoding="utf-8")
