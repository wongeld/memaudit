"""Offline city-by-occupation counts for the synthetic candidate pool."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import TypedDict

from pipeline.attacks import normalize
from pipeline.profiles import Profile


class CountRow(TypedDict):
    country: str
    city: str
    occupation: str
    count: int


def regional_counts(profiles: dict[str, Profile]) -> list[CountRow]:
    counts: Counter[tuple[str, str, str]] = Counter()
    countries: dict[str, str] = {}
    cities: dict[tuple[str, str], str] = {}
    occupations: dict[tuple[str, str], str] = {}
    for profile in profiles.values():
        country, city, occupation = (normalize(value) for value in
                                     (profile.country, profile.city, profile.occupation))
        if not country or not city or not occupation:
            raise ValueError(f"Profile {profile.profile_id} is missing a country, city or occupation.")
        countries.setdefault(country, profile.country.strip())
        cities.setdefault((country, city), profile.city.strip())
        occupations.setdefault((country, occupation), profile.occupation.strip())
        counts[(country, city, occupation)] += 1

    return [
        {"country": countries[country], "city": cities[(country, city)],
         "occupation": occupations[(country, occupation)], "count": counts[(country, city, occupation)]}
        for country in sorted(countries)
        for city in sorted(city for parent, city in cities if parent == country)
        for occupation in sorted(occupation for parent, occupation in occupations if parent == country)
    ]


def draw_heatmap(country: str, rows: list[CountRow], destination: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    cities = sorted({row["city"] for row in rows}, key=normalize)
    occupations = sorted({row["occupation"] for row in rows}, key=normalize)
    counts = {(row["city"], row["occupation"]): row["count"] for row in rows}
    values = [[counts[(city, occupation)] for city in cities] for occupation in occupations]
    categories = [[0 if n == 0 else 1 if n == 1 else 2 if n < 5 else 3 for n in row]
                  for row in values]
    colors = ["#eeeeee", "#d65f5f", "#efb84c", "#69a99b"]
    fig, axis = plt.subplots(figsize=(max(7, 4 + len(cities) * 1.25),
                                      max(4.5, 2.9 + len(occupations) * .46)),
                             layout="constrained")
    axis.imshow(categories, cmap=ListedColormap(colors), vmin=0, vmax=3, aspect="auto")
    axis.set_xticks(range(len(cities)), cities)
    axis.set_yticks(range(len(occupations)), occupations)
    axis.set_xlabel("City")
    axis.set_ylabel("Occupation")
    axis.set_title(f"{country}: {sum(row['count'] for row in rows)} synthetic profiles\n"
                   "Profiles sharing each city and occupation")
    for y, row in enumerate(values):
        for x, count in enumerate(row):
            axis.text(x, y, str(count) if count else "-", ha="center", va="center", fontsize=10)
    axis.set_xticks([x - .5 for x in range(1, len(cities))], minor=True)
    axis.set_yticks([y - .5 for y in range(1, len(occupations))], minor=True)
    axis.grid(which="minor", color="white", linewidth=1.5)
    axis.tick_params(which="minor", bottom=False, left=False)
    axis.legend(handles=[Patch(facecolor=color, label=label) for color, label in zip(
        colors, ("0 profiles", "1 profile", "2-4 profiles", "5+ profiles"), strict=True)],
        loc="upper center", bbox_to_anchor=(.5, -.14), ncols=4, frameon=False)
    fig.savefig(destination, dpi=180)
    plt.close(fig)


def write_heatmaps(profiles: dict[str, Profile], destination: Path) -> None:
    rows = regional_counts(profiles)
    if not rows:
        raise ValueError("No synthetic profiles to plot.")
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / "city_occupation_counts.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("country", "city", "occupation", "count"))
        writer.writeheader()
        writer.writerows(rows)

    countries = sorted({row["country"] for row in rows}, key=normalize)
    index = []
    for number, country in enumerate(countries, 1):
        selected = [row for row in rows if row["country"] == country]
        filename = f"region_{number:03d}.png"
        draw_heatmap(country, selected, destination / filename)
        index.append(f"- {country}: {sum(row['count'] for row in selected)} profiles "
                     f"([{filename}]({filename})).")
    lines = [
        "# Synthetic city and occupation heatmaps", "",
        f"These charts represent all {len(profiles)} profiles in the current synthetic pool, "
        "grouped by country. Each cell counts profiles sharing the named city and occupation; "
        "a dash means zero. `city_occupation_counts.csv` includes the zero-count cells.", "",
        "If both attributes were already known, a cell with one profile would be unique "
        "only within this synthetic pool. It is not proof of identification, that an attacker "
        "learned either attribute, or of real-world risk. The dataset is small and not "
        "representative of a real population.", "",
        "These are categorical grids, not geographic maps: cities are not positioned by "
        "coordinates. City and occupation names are normalized for matching; this does not "
        "resolve geographic ambiguity. No Step 3 answers, model calls, map services or "
        "geographic lookups are used.", "",
        "## Countries", "", *index, "",
    ]
    (destination / "report.md").write_text("\n".join(lines), encoding="utf-8")
