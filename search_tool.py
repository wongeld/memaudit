"""
search_tool.py - keyless web-search tool for the step5 privacy-risk test.

Sources (all free, no API key):
  * DuckDuckGo text search   (pip package `ddgs`)
  * Wikipedia search API      (via `requests`)
  * OpenStreetMap Nominatim   (geocoding a place -> country, via `requests`)

Everything is cached on disk so re-runs are cheap and polite to the services.

Quick manual test:
    python search_tool.py "secondary schools Nairobi Kenya"
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import requests

UA = "privacy-risk-research/0.1 (academic re-identification study)"

# Best-effort DuckDuckGo region codes. Unknown -> worldwide ("wt-wt").
DDG_REGIONS = {
    "kenya": "ke-en", "nigeria": "ng-en", "south africa": "za-en",
    "united states": "us-en", "united kingdom": "uk-en", "india": "in-en",
    "australia": "au-en", "canada": "ca-en", "germany": "de-de",
    "france": "fr-fr", "spain": "es-es", "italy": "it-it", "brazil": "br-pt",
    "mexico": "mx-es", "japan": "jp-jp", "china": "cn-zh", "ireland": "ie-en",
    "new zealand": "nz-en", "philippines": "ph-en", "pakistan": "pk-en",
    "singapore": "sg-en", "netherlands": "nl-nl", "turkey": "tr-tr",
}


class ProfileSearchTool:
    def __init__(self, cache_path: str | Path = Path("simulation") / ".cache" / "search_cache.json",
                 delay: float = 1.0, verbose: bool = True):
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.verbose = verbose
        self._last_call = 0.0
        self.cache: dict = {}
        if self.cache_path.exists():
            try:
                self.cache = json.loads(self.cache_path.read_text())
            except Exception:
                self.cache = {}

    # ---------------------------------------------------------------- utils
    def _key(self, *parts) -> str:
        return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()

    def _save(self):
        self.cache_path.write_text(json.dumps(self.cache))

    def _wait(self):
        dt = time.time() - self._last_call
        if dt < self.delay:
            time.sleep(self.delay - dt)
        self._last_call = time.time()

    def _log(self, msg):
        if self.verbose:
            print(f"    [search] {msg}", file=sys.stderr)

    def public_places(self, query: str, limit: int = 20, viewbox: str | None = None) -> list[dict]:
        """Search public OpenStreetMap places, preserving their type and coordinates."""
        key = self._key("nominatim-public-v2", query, limit, viewbox)
        if key in self.cache:
            return self.cache[key]
        self._wait()
        params = {"q": query, "format": "jsonv2", "addressdetails": 1, "limit": limit,
                  "accept-language": "en"}
        if viewbox:
            params.update({"viewbox": viewbox, "bounded": 1})
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers={"User-Agent": UA}, timeout=20,
        )
        response.raise_for_status()
        results = response.json()
        if not isinstance(results, list):
            raise ValueError(f"Unexpected Nominatim response for {query!r}")
        self.cache[key] = results
        self._save()
        return results

    # ------------------------------------------------------------ DuckDuckGo
    def web(self, query: str, max_results: int = 8, country: str | None = None) -> list[dict]:
        region = DDG_REGIONS.get((country or "").lower().strip(), "wt-wt")
        k = self._key("ddg", query, region, max_results)
        if self.cache.get(k):
            return self.cache[k]
        try:
            try:
                from ddgs import DDGS
            except ImportError:  # old package name
                from duckduckgo_search import DDGS
        except ImportError:
            self._log("ddgs not installed -> `uv add ddgs`")
            return []
        out: list[dict] = []
        for attempt in range(3):
            try:
                self._wait()
                res = DDGS().text(query, region=region, max_results=max_results)
                out = [{"source": "ddg", "query": query, "title": r.get("title", ""),
                        "url": r.get("href") or r.get("url", ""), "snippet": r.get("body", "")}
                       for r in (res or [])]
                break
            except Exception as e:  # rate limits etc.
                self._log(f"ddg attempt {attempt+1} failed: {e}")
                region = "wt-wt"
                time.sleep(2 * (attempt + 1))
        if out:
            self.cache[k] = out
            self._save()
        return out

    # ------------------------------------------------------------- Wikipedia
    def wikipedia(self, query: str, n: int = 3) -> list[dict]:
        k = self._key("wiki", query, n)
        if self.cache.get(k):
            return self.cache[k]
        out: list[dict] = []
        try:
            self._wait()
            r = requests.get("https://en.wikipedia.org/w/api.php", timeout=15,
                             headers={"User-Agent": UA},
                             params={"action": "query", "list": "search", "srsearch": query,
                                     "srlimit": n, "format": "json"})
            r.raise_for_status()
            for it in r.json().get("query", {}).get("search", []):
                title = it["title"]
                snippet = (it.get("snippet", "").replace('<span class="searchmatch">', "")
                           .replace("</span>", ""))
                out.append({"source": "wikipedia", "query": query, "title": title,
                            "url": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
                            "snippet": snippet})
        except Exception as e:
            self._log(f"wikipedia failed: {e}")
        if out:
            self.cache[k] = out
            self._save()
        return out

    # ------------------------------------------------------ OSM / Nominatim
    def geocode(self, place: str) -> dict:
        """place -> {'country':..., 'display':..., 'lat':..., 'lon':...}  ({} if unknown)."""
        k = self._key("osm", place)
        if k in self.cache:
            return self.cache[k]
        out: dict = {}
        try:
            time.sleep(1.1)  # Nominatim policy: max 1 request/second
            r = requests.get("https://nominatim.openstreetmap.org/search", timeout=15,
                             headers={"User-Agent": UA},
                             params={"q": place, "format": "json", "limit": 1,
                                     "addressdetails": 1, "accept-language": "en"})
            js = r.json()
            if js:
                out = {"country": js[0].get("address", {}).get("country", ""),
                       "display": js[0].get("display_name", ""),
                       "lat": js[0].get("lat"), "lon": js[0].get("lon")}
        except Exception as e:
            self._log(f"nominatim failed: {e}")
        self.cache[k] = out
        self._save()
        return out

    # ---------------------------------------------------------- main entry
    def search(self, queries: list[str], country: str | None = None,
               per_query: int = 6, use_wikipedia: bool = True,
               max_total: int = 40) -> list[dict]:
        """Run all queries, de-duplicate by URL, return a flat list of results."""
        seen, results = set(), []
        for q in queries:
            batch = self.web(q, per_query, country)
            if use_wikipedia:
                batch = batch + self.wikipedia(q, 2)
            self._log(f"{len(batch):>2} hits  <- {q}")
            for r in batch:
                if r["url"] and r["url"] not in seen:
                    seen.add(r["url"])
                    results.append(r)
            if len(results) >= max_total:
                break
        return results[:max_total]


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "secondary schools Nairobi Kenya"
    tool = ProfileSearchTool(cache_path=Path("simulation") / ".cache" / "search_cache.json")
    for r in tool.search([q]):
        print(f"- [{r['source']}] {r['title']}\n  {r['url']}\n  {r['snippet'][:160]}\n")
    print(tool.geocode(q))