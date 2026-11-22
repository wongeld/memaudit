"""Map aggregate synthetic profile counts using public city centers."""

from __future__ import annotations

import csv
import math
import re
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

import requests

from .attacks import normalize
from .profiles import Profile

USER_AGENT = "memaudit-synthetic-simulation/1.0 (academic privacy research)"
PRIVATE_TERMS = re.compile(r"\b(home|house|residence|address|apartment|private)\b", re.IGNORECASE)


def public_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    plain = "".join(character for character in decomposed if not unicodedata.combining(character))
    plain = re.sub(r"[^\w\s]", "", plain)
    return re.sub(r"\s+", " ", plain).strip().removeprefix("the ")


class PublicCitySearch:
    def __init__(self, cache: Path):
        import json

        self.path = cache
        self.cache = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
        if not isinstance(self.cache, dict):
            raise ValueError(f"Invalid public-city cache: {cache}")
        self.last_call = 0.0

    def search(self, query: str, *, namedetails: bool = False) -> list[dict]:
        import json

        cache_key = f"{query}|namedetails" if namedetails else query
        if cache_key in self.cache:
            results = self.cache[cache_key]
        else:
            time.sleep(max(0.0, 1.1 - (time.monotonic() - self.last_call)))
            params = {"q": query, "format": "jsonv2", "addressdetails": 1, "limit": 20,
                      "accept-language": "en"}
            if namedetails:
                params["namedetails"] = 1
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params=params,
                headers={"User-Agent": USER_AGENT}, timeout=20,
            )
            self.last_call = time.monotonic()
            response.raise_for_status()
            results = response.json()
            if not isinstance(results, list):
                raise ValueError(f"Unexpected public-city response for {query!r}")
            self.cache[cache_key] = results
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")
        if not isinstance(results, list):
            raise ValueError(f"Invalid cached public-city response for {query!r}")
        return results


def coordinates(item: dict) -> tuple[float, float] | None:
    try:
        lat, lon = float(item["lat"]), float(item["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return lat, lon


def distance_km(left: tuple[float, float], right: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, left)
    lat2, lon2 = map(math.radians, right)
    value = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(min(1.0, value)))


def resolve_city(search: PublicCitySearch, city: str, country: str, neighborhoods: set[str]) -> tuple | None:
    def names(item: dict) -> set[str]:
        values = [item.get("name", "")]
        for key, value in item.get("namedetails", {}).items():
            if isinstance(value, str) and key.split(":", 1)[0] in {"name", "alt_name", "official_name"}:
                values.extend(re.split(r"[;,]", value))
        return {public_name(re.sub(r"^\(\d+\)\s*", "", value)) for value in values}

    def matching(results: list[dict]) -> list[dict]:
        return [
        item for item in results
        if public_name(city) in names(item)
        and normalize(item.get("address", {}).get("country", "")) == normalize(country)
        and item.get("category") in {"place", "boundary"}
        and item.get("type") in {"city", "town", "village", "municipality", "administrative"}
        and coordinates(item) is not None
        ]

    query = f"{city}, {country}"
    centers = matching(search.search(query))
    if not centers:
        centers = matching(search.search(query, namedetails=True))
    preferred = [item for item in centers if item["category"] == "place" and item["type"] in {"city", "town"}]
    centers = preferred or [item for item in centers if item["category"] == "boundary"] or centers
    if not centers:
        return None
    locations = [coordinates(item) for item in centers]
    if all(distance_km(locations[0], location) <= 20 for location in locations[1:]):
        return locations[0]

    possible = set()
    for name in sorted(neighborhoods):
        if not name or len(name) > 100 or re.search(r"\d|[,\r\n@\[\]]", name) or PRIVATE_TERMS.search(name):
            continue
        matches = [
            coordinates(item) for item in search.search(f"{name}, {city}, {country}")
            if public_name(item.get("name", "")) == public_name(name)
            and normalize(item.get("address", {}).get("country", "")) == normalize(country)
            and item.get("category") == "place"
            and item.get("type") in {"neighbourhood", "suburb", "quarter", "village"}
            and coordinates(item) is not None
        ]
        possible.update(i for i, center in enumerate(locations)
                        if any(distance_km(center, match) <= 20 for match in matches))
    selected = [locations[i] for i in sorted(possible)]
    if selected and all(distance_km(selected[0], location) <= 20 for location in selected[1:]):
        return selected[0]
    return None


def tile_xy(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    lat = max(-85.0511, min(85.0511, lat))
    scale = 2 ** zoom
    return ((lon + 180) / 360 * scale,
            (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * scale)


def draw_world(points: list[dict], destination: Path, tile_dir: Path, total: int) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not points:
        raise ValueError("No verified public city centers are available for the candidate map")
    lats = [point["latitude"] for point in points]
    lons = [point["longitude"] for point in points]
    lat_pad = max((max(lats) - min(lats)) * .12, 3)
    lon_pad = max((max(lons) - min(lons)) * .08, 3)
    north, south = min(85, max(lats) + lat_pad), max(-85, min(lats) - lat_pad)
    west, east = max(-180, min(lons) - lon_pad), min(180, max(lons) + lon_pad)
    for zoom in range(12, 1, -1):
        x1, y1 = tile_xy(north, west, zoom)
        x2, y2 = tile_xy(south, east, zoom)
        if (math.floor(x2) - math.floor(x1) + 1) * (math.floor(y2) - math.floor(y1) + 1) <= 32:
            break
    fig = plt.figure(figsize=(16, 8))
    axis = fig.add_axes((.015, .07, .97, .86))
    tile_dir.mkdir(parents=True, exist_ok=True)
    for x in range(math.floor(x1), math.floor(x2) + 1):
        for y in range(math.floor(y1), math.floor(y2) + 1):
            tile = tile_dir / f"{zoom}_{x}_{y}.png"
            if not tile.exists():
                response = requests.get(
                    f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png",
                    headers={"User-Agent": USER_AGENT}, timeout=20,
                )
                response.raise_for_status()
                tile.write_bytes(response.content)
            axis.imshow(plt.imread(tile), extent=(x, x + 1, y + 1, y), zorder=0)
    axis.set_xlim(x1, x2)
    axis.set_ylim(y2, y1)
    axis.set_aspect("auto")
    axis.axis("off")
    fig.canvas.draw()
    legend = []
    label_positions = []
    offsets = [(0, 0)] + [(dx, dy) for radius in (18, 36, 54, 72)
                          for dx, dy in ((0, radius), (0, -radius), (radius, 0), (-radius, 0),
                                         (radius, radius), (-radius, -radius))]
    for index, point in enumerate(points, 1):
        x, y = tile_xy(point["latitude"], point["longitude"], zoom)
        axis.scatter(x, y, s=35 + 8 * point["count"], c="#c8102e", edgecolors="white", linewidths=1, zorder=3)
        pixel_x, pixel_y = axis.transData.transform((x, y))
        offset = next(((dx, dy) for dx, dy in offsets
                       if all(abs(pixel_x + dx - px) >= 20 or abs(pixel_y + dy - py) >= 17
                              for px, py in label_positions)), offsets[-1])
        label_positions.append((pixel_x + offset[0], pixel_y + offset[1]))
        axis.annotate(str(index), (x, y), xytext=(offset[0] * 72 / fig.dpi, offset[1] * 72 / fig.dpi),
                      textcoords="offset points", color="white", ha="center", va="center", fontsize=7,
                      weight="bold", zorder=4, bbox={"boxstyle": "circle,pad=0.25", "facecolor": "#c8102e",
                                                     "edgecolor": "white"},
                      arrowprops={"arrowstyle": "-", "color": "#c8102e", "lw": .8} if offset != (0, 0) else None)
        legend.append(f"{index:02}. {point['city']}, {point['country']}  ({point['count']})")
    axis.text(.40, .97, "\n".join(legend), transform=axis.transAxes, va="top", fontsize=8,
              bbox={"facecolor": "white", "alpha": .88, "edgecolor": "#777777", "pad": 6})
    fig.suptitle(f"Synthetic candidates by city ({sum(point['count'] for point in points)}/{total} mapped)",
                 fontsize=15, y=.98)
    fig.text(.015, .025, "Counts at public city centers; not individual locations. © OpenStreetMap contributors.",
             fontsize=9)
    fig.savefig(destination, dpi=180)
    plt.close(fig)


def map_candidates(profiles: dict[str, Profile], out: Path) -> tuple[int, list[str]]:
    grouped: dict[tuple[str, str], list[Profile]] = defaultdict(list)
    for profile in profiles.values():
        grouped[(profile.city, profile.country)].append(profile)
    search = PublicCitySearch(out / ".cache" / "city_search.json")
    points = []
    missing = []
    rows = []
    for (city, country), members in sorted(grouped.items()):
        location = resolve_city(search, city, country, {profile.neighborhood for profile in members})
        row = {"city": city, "country": country, "count": len(members), "latitude": "", "longitude": "",
               "mapped": location is not None}
        if location is None:
            missing.append(f"{city}, {country}: public city center was unavailable or ambiguous ({len(members)}).")
        else:
            row.update(latitude=location[0], longitude=location[1])
            points.append(row)
        rows.append(row)
    with (out / "candidate_cities.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["city", "country", "count", "latitude", "longitude", "mapped"])
        writer.writeheader()
        writer.writerows(rows)
    if points:
        draw_world(points, out / "candidate_map.png", out / ".cache" / "tiles", len(profiles))
    return sum(point["count"] for point in points), missing
