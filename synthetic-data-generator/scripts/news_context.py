"""
Python port of the TypeScript news-context scraper.

Install:
    pip install requests beautifulsoup4 readability-lxml

Usage:
    from scripts.news_context import fetch_news_context

    result = fetch_news_context(
        language="en",
        region="Kenya",
        theme="work",
        query="new job opportunities",
        max_articles=6,
    )
    print(result["text"])

This is a standalone Python module. The original Pi coding-agent registration
(TypeBox schemas, pi.registerTool, onUpdate) is replaced by ordinary functions.
fetch_news_context returns formatted full article text in "text" and article
metadata in "details".
"""

from __future__ import annotations

import json
import re
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from urllib.parse import (
    parse_qs, urlencode, urljoin, urlparse, urlunparse, parse_qsl
)
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from readability import Document

logger = logging.getLogger(__name__)

LANG_NAMES = {"en": "English", "sw": "Swahili", "am": "Amharic"}
THEMES = ("work", "travel", "school", "shopping", "family", "daily_planning")
CATEGORIES = (
    "general", "politics", "business", "sports", "health", "crime",
    "education", "entertainment", "world", "local", "lifestyle",
    "environment", "opinion", "family", "travel", "shopping",
)

THEME_CATEGORIES = {
    "work": [("business", 2), ("local", 0), ("general", 0)],
    "travel": [("travel", 3), ("local", 0), ("world", 0), ("general", 0)],
    "school": [("education", 3), ("local", 0), ("general", 0)],
    "shopping": [("shopping", 3), ("business", 1), ("lifestyle", 1), ("general", 0)],
    "family": [("family", 3), ("lifestyle", 1), ("health", 1), ("general", 0)],
    "daily_planning": [("lifestyle", 2), ("health", 2), ("local", 0), ("general", 0)],
}

THEME_KEYWORDS = {
    "en": {
        "work": ["job", "employ", "salary", "salaries", "wage", "workers", "labour", "labor", "hiring", "layoff", "career", "workplace", "business", "entrepreneur", "strike", "company"],
        "travel": ["travel", "flight", "airline", "airport", "passenger", "road", "highway", "bus ", "matatu", "train", "railway", "tourism", "tourist", "visa", "border", "ferry", "traffic"],
        "school": ["school", "student", "pupil", "teacher", "education", "exam", "university", "college", "kcse", "kcpe", "curriculum", "fees", "tuition", "scholarship", "bursary"],
        "shopping": ["price", "market", "shop", "supermarket", "retail", "consumer", "cost of living", "inflation", "goods", "food prices", "maize flour", "fuel", "discount", "customers", "vendors"],
        "family": ["family", "families", "parent", "child", "marriage", "wedding", "couple", "mother", "father", "relationship", "divorce", "household", "baby", "teen"],
        "daily_planning": ["weather", "rain", "forecast", "water", "power outage", "electricity", "transport", "commute", "budget", "health", "clinic", "schedule", "routine", "traffic", "holiday", "timetable"],
    },
    "sw": {
        "work": ["ajira", "kazi", "wafanyakazi", "mshahara", "mishahara", "biashara", "wafanyabiashara", "ajiri", "mgomo", "kampuni", "wawekezaji"],
        "travel": ["safari", "usafiri", "barabara", "ndege", "abiria", "matatu", "treni", "reli", "utalii", "watalii", "visa", "mpaka", "feri", "msongamano", "basi"],
        "school": ["shule", "wanafunzi", "walimu", "mwalimu", "elimu", "mtihani", "mitihani", "chuo", "kcse", "kcpe", "ada ", "masomo", "udhamini", "cbc", "tsc"],
        "shopping": ["bei", "soko", "ununuzi", "duka", "maduka", "wateja", "bidhaa", "unga", "mafuta", "gharama ya maisha", "mfumko", "mfumuko", "sukari", "wauzaji", "punguzo"],
        "family": ["familia", "watoto", "mtoto", "ndoa", "harusi", "wazazi", "mama", "baba", "malezi", "talaka", "mapenzi", "mume", "mke", "wanandoa", "ndugu"],
        "daily_planning": ["hali ya hewa", "mvua", "jua", "maji", "mgao", "umeme", "usafiri", "bajeti", "afya", "kliniki", "ratiba", "msongamano", "likizo", "mafuriko", "ukame", "chakula"],
    },
    "am": {
        "work": ["ስራ", "ሥራ", "ቅጥር", "ሰራተኛ", "ሠራተኞች", "ደመወዝ", "ንግድ", "ኢንቨስትመንት", "ኩባንያ", "ሥራ አጥ"],
        "travel": ["ጉዞ", "በረራ", "አየር መንገድ", "መንገድ", "ተጓዦች", "ባቡር", "ቱሪዝም", "ጎብኚ", "ቪዛ", "ድንበር", "መጓጓዣ", "ትራንስፖርት"],
        "school": ["ትምህርት", "ተማሪ", "መምህር", "መምህራን", "ዩኒቨርሲቲ", "ፈተና", "ኮሌጅ"],
        "shopping": ["ገበያ", "ዋጋ", "ሸመታ", "ሸማች", "ሸቀጣ", "መደብር", "ነጋዴ", "ዘይት", "ስኳር", "የኑሮ ውድነት", "ንረት"],
        "family": ["ቤተሰብ", "ልጆች", "ልጅ", "ጋብቻ", "ሰርግ", "ወላጆች", "እናት", "አባት", "ፍቺ", "ትዳር", "እናቶች"],
        "daily_planning": ["የአየር ሁኔታ", "ዝናብ", "ውሃ", "ኤሌክትሪክ", "መብራት", "ነዳጅ", "ጤና", "ክሊኒክ", "በጀት", "ትራንስፖርት", "ጎርፍ", "ድርቅ", "ምግብ"],
    },
}

CATEGORY_KEYWORDS = {
    "en": {
        "crime": ["police", "arrest", "murder", "court", "robbery", "suspect", "dci", "killed", "charged", "jail", "theft", "kidnap"],
        "sports": ["match", "league", "goal", "football", "athlete", "marathon", "rugby", "cup", "coach", "tournament"],
        "politics": ["election", "president", "parliament", "senate", "minister", "opposition", "party", "mp ", "governor"],
        "health": ["health", "hospital", "disease", "doctor", "vaccine", "outbreak", "patients", "medicine", "nurses"],
        "business": ["economy", "business", "bank", "shares", "market", "trade", "investors", "inflation", "tax"],
        "entertainment": ["film", "music", "artist", "concert", "celebrity", "movie", "album", "actor"],
        "environment": ["climate", "environment", "wildlife", "pollution", "drought", "floods", "forest"],
        "education": ["school", "student", "teacher", "university", "exam", "education"],
    },
    "sw": {
        "crime": ["polisi", "mauaji", "mahakama", "wizi", "mshukiwa", "dci", "kukamatwa", "aliuawa", "jela", "ujambazi", "mashtaka"],
        "sports": ["mechi", "ligi", "goli", "soka", "wanariadha", "michezo", "kocha", "mashindano", "kombe", "riadha"],
        "politics": ["uchaguzi", "rais", "bunge", "siasa", "serikali", "waziri", "upinzani", "chama", "gavana", "seneta"],
        "health": ["afya", "ugonjwa", "hospitali", "dawa", "chanjo", "daktari", "wagonjwa", "mlipuko"],
        "business": ["uchumi", "biashara", "benki", "hisa", "soko", "wawekezaji", "kodi", "mfumuko"],
        "entertainment": ["filamu", "muziki", "msanii", "tamasha", "mwigizaji", "albamu"],
        "environment": ["tabianchi", "mazingira", "wanyamapori", "uchafuzi", "ukame", "mafuriko", "msitu"],
        "education": ["shule", "wanafunzi", "walimu", "chuo", "mtihani", "elimu"],
    },
    "am": {
        "crime": ["ፖሊስ", "ግድያ", "ፍርድ ቤት", "ዝርፊያ", "ተጠርጣሪ", "ታሳሪ", "እስር", "ወንጀል"],
        "sports": ["እግር ኳስ", "ጨዋታ", "ሊግ", "አትሌት", "ስፖርት", "ውድድር", "ማራቶን"],
        "politics": ["ምርጫ", "መንግስት", "ፓርላማ", "ፖለቲካ", "ጠቅላይ ሚኒስትር", "ተቃዋሚ", "ፓርቲ"],
        "health": ["ጤና", "በሽታ", "ሆስፒታል", "ክትባት", "ሐኪም", "ታማሚ", "ወረርሽኝ"],
        "business": ["ኢኮኖሚ", "ንግድ", "ባንክ", "ኢንቨስትመንት", "ዋጋ ንረት", "ታክስ"],
        "entertainment": ["ፊልም", "ሙዚቃ", "አርቲስት", "ኮንሰርት"],
        "environment": ["የአየር ንብረት", "አካባቢ", "ብክለት", "ድርቅ", "ጎርፍ", "ደን"],
        "education": ["ትምህርት", "ተማሪ", "መምህር", "ዩኒቨርሲቲ", "ፈተና"],
    },
}

REGION_ALIASES = {
    "kenya": ["kenya", "nairobi", "mombasa", "kisumu", "nakuru", "eldoret", "kenyan"],
    "tanzania": ["tanzania", "dar es salaam", "dodoma", "zanzibar", "arusha", "mwanza"],
    "uganda": ["uganda", "kampala", "entebbe"],
    "rwanda": ["rwanda", "kigali", "rwandan"],
    "burundi": ["burundi", "bujumbura", "gitega"],
    "ethiopia": ["ethiopia", "addis ababa", "ኢትዮጵያ", "አዲስ አበባ", "አማራ", "ኦሮሚያ", "ትግራይ"],
    "somalia": ["somalia", "mogadishu", "somaliland", "puntland"],
    "south sudan": ["south sudan", "juba"],
    "drc": ["congo", "drc", "kinshasa", "goma"],
}
REGION_ALIASES["east africa"] = ["east africa", "eac"] + sum(
    [REGION_ALIASES[k] for k in ("kenya", "tanzania", "uganda", "rwanda", "burundi")], []
)
AFRICAN_REGION_KEYS = set(REGION_ALIASES)

BBC_NOISE = [
    "[data-component='links-block']", "[data-component='related-content']",
    "[data-component='byline-block']", "[data-component='topic-list']",
]

@dataclass
class Source:
    id: str
    name: str
    lang: str
    hosts: list[str]
    base: str
    search_scope: str
    pages: dict[str, list[str]] = field(default_factory=dict)
    feeds: dict[str, list[str]] = field(default_factory=dict)
    article_pattern: Optional[str] = None
    content_selectors: list[str] = field(default_factory=list)
    remove_selectors: list[str] = field(default_factory=list)

    def is_article_url(self, url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.hostname.removeprefix("www.") if parsed.hostname else ""
        if host not in self.hosts:
            return False
        return bool(self.article_pattern and re.search(self.article_pattern, parsed.path))

SOURCES = [
    Source("taifaleo", "Taifa Leo", "sw", ["taifaleo.nation.co.ke"], "https://taifaleo.nation.co.ke", "taifaleo.nation.co.ke",
        pages={
            "general": ["/"], "local": ["/sehemu/habari/habari-za-kaunti/", "/sehemu/habari/habari-za-kitaifa/"],
            "politics": ["/sehemu/siasa/"], "sports": ["/sehemu/michezo/", "/sehemu/dimba/"],
            "health": ["/sehemu/makala/afya-na-jamii/"], "education": ["/sehemu/makala/lugha-fasihi-elimu/", "/nieshuleni/"],
            "world": ["/sehemu/habari/kimataifa/"], "business": ["/sehemu/makala/akili-mali/", "/sehemu/washirika/"],
            "shopping": ["/sehemu/makala/bambika/", "/sehemu/makala/akili-mali/"],
            "family": ["/sehemu/makala/pambo/", "/sehemu/makala/shangazi-akujibu/"],
            "lifestyle": ["/sehemu/makala/pambo/", "/sehemu/makala/afya-na-jamii/", "/sehemu/makala/bambika/"],
            "entertainment": ["/sehemu/dondoo/"], "opinion": ["/sehemu/maoni/"],
        }, article_pattern=r"^/(?!sehemu|wp-content|wp-json|tag|author|category|page|video|bi-taifa|nieshuleni)[^/]+/.+|^/[^/]+/[^/]+$",
        content_selectors=["article .entry-content", ".entry-content", ".single-content", ".post-content", ".article-content", ".article-body", "[itemprop='articleBody']", "article"],
        remove_selectors=["[class*='related']", "[class*='share']", "[class*='social']", "[class*='newsletter']", "[id*='taboola']", "[class*='soma-pia']"]),
    Source("standard", "The Standard (Kenya)", "en", ["standardmedia.co.ke", "thestandard.ke"], "https://www.standardmedia.co.ke", "standardmedia.co.ke",
        pages={
            "general": ["/"], "local": ["/category/1/counties"], "politics": ["/category/3/politics"], "business": ["/business"],
            "world": ["/category/5/world", "/category/23/africa"], "health": ["/health", "/category/41/health-science", "/category/573/nutrition-wellness"],
            "sports": ["/sports", "/sports/category/29/football", "/sports/category/378/athletics"], "education": ["/category/56/education"],
            "entertainment": ["/entertainment"], "lifestyle": ["/evewoman/category/273/living", "/entertainment/category/126/lifestyle", "/evewoman/category/416/wellness"],
            "environment": ["/category/63/environment"], "opinion": ["/category/7/opinion", "/category/74/columnists"],
            "crime": ["/category/763/courts"], "family": ["/evewoman/category/262/parenting", "/evewoman/category/264/relationships", "/gender/"],
            "travel": ["/evewoman/category/307/leisure-and-travel"], "shopping": ["/evewoman/category/265/fashion-and-beauty", "/evewoman/category/267/food"],
        }, article_pattern=r"/article/\d+/", content_selectors=[".article-content", ".main-article", ".article-body", ".story-body", ".article-text", "[itemprop='articleBody']", "article", "main"],
        remove_selectors=["[class*='related']", "[class*='share']", "[class*='newsletter']", "[class*='advert']", "[class*='comment']", "[class*='read-also']"]),
    Source("bbc_sw", "BBC News Swahili", "sw", ["bbc.com"], "https://www.bbc.com", "bbc.com/swahili",
        pages={"general": ["/swahili"]}, feeds={"general": ["https://feeds.bbci.co.uk/swahili/rss.xml"]},
        article_pattern=r"^/swahili/(articles/[a-z0-9]+|(?!media-)[a-z-]+-\d{5,})/?$",
        content_selectors=["main [data-component='text-block']", "article", "main"], remove_selectors=BBC_NOISE),
    Source("bbc_am", "BBC News Amharic", "am", ["bbc.com"], "https://www.bbc.com", "bbc.com/amharic",
        pages={"general": ["/amharic"]}, feeds={"general": ["https://feeds.bbci.co.uk/amharic/rss.xml"]},
        article_pattern=r"^/amharic/(articles/[a-z0-9]+|(?!media-)[a-z-]+-\d{5,})/?$",
        content_selectors=["main [data-component='text-block']", "article", "main"], remove_selectors=BBC_NOISE),
    Source("bbc_en", "BBC News", "en", ["bbc.com"], "https://www.bbc.com", "bbc.com/news",
        pages={"general": ["/news"], "business": ["/business"], "travel": ["/travel"], "sports": ["/sport"], "environment": ["/earth"]},
        feeds={
            "general": ["https://feeds.bbci.co.uk/news/rss.xml"], "world": ["https://feeds.bbci.co.uk/news/world/rss.xml"],
            "business": ["https://feeds.bbci.co.uk/news/business/rss.xml"], "health": ["https://feeds.bbci.co.uk/news/health/rss.xml"],
            "education": ["https://feeds.bbci.co.uk/news/education/rss.xml"], "politics": ["https://feeds.bbci.co.uk/news/politics/rss.xml"],
            "entertainment": ["https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml"],
            "environment": ["https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"],
            "sports": ["https://feeds.bbci.co.uk/sport/rss.xml"], "local": ["https://feeds.bbci.co.uk/news/world/africa/rss.xml"],
        }, article_pattern=r"^/(news|sport|travel|culture|future|worklife|innovation|business|earth)/(articles/[a-z0-9]+|article/[a-z0-9-]+|(?!media-|av-)[a-z0-9_-]*-\d{6,})/?$",
        content_selectors=["main [data-component='text-block']", "article", "main"], remove_selectors=BBC_NOISE),
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
ACCEPT_LANGUAGE = {"en": "en-GB,en;q=0.9", "sw": "sw,en;q=0.7", "am": "am,en;q=0.7"}
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

def squash(value: str) -> str:
    return re.sub(r"[\u00a0\s]+", " ", value or "").strip()

def canonical_url(raw: str) -> Optional[str]:
    try:
        p = urlparse(raw)
        if not p.scheme or not p.netloc:
            return None
        host = p.hostname or ""
        if host.endswith("bbc.co.uk"):
            host = "www.bbc.com"
        netloc = host
        if p.port:
            netloc += f":{p.port}"
        query = [
            (k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
            if not re.match(r"^(utm_|at_|xtor|ns_|fbclid|gclid|ocid|share)", k, re.I)
        ]
        path = p.path.rstrip("/") or "/"
        return urlunparse(("https", netloc, path, "", urlencode(query), ""))
    except Exception:
        return None

def slug_words(url: str) -> str:
    try:
        return re.sub(r"[-_]+", " ", urlparse(url).path.rstrip("/").split("/")[-1])
    except Exception:
        return ""

def title_from_slug(url: str) -> str:
    words = slug_words(url)
    return words[:1].upper() + words[1:] if words else url

def count_hits(text: str, keywords: list[str]) -> int:
    low = text.lower()
    return sum(1 for word in keywords if word.lower() in low)

def count_occurrences(text: str, terms: list[str]) -> int:
    low, total = text.lower(), 0
    for term in terms:
        start = 0
        needle = term.lower()
        if not needle:
            continue
        while (idx := low.find(needle, start)) != -1 and total < 50:
            total += 1
            start = idx + len(needle)
    return total

def normalize_lang(raw: str) -> Optional[str]:
    s = raw.strip().lower()
    if s in ("en", "eng", "english"): return "en"
    if s in ("sw", "swa", "swahili", "kiswahili"): return "sw"
    if s in ("am", "amh", "amharic", "አማርኛ"): return "am"
    return None

def resolve_region(region: Optional[str]) -> Optional[dict]:
    if not region or not region.strip():
        return None
    value = region.strip()
    low = value.lower()
    for key, aliases in REGION_ALIASES.items():
        if key == low or low in aliases:
            return {"label": value, "key": key, "terms": list(dict.fromkeys([key, *aliases]))}
    return {"label": value, "terms": [low]}

def fetch_page(url: str, *, lang: str = "en", timeout: int = 20,
               method: str = "GET", data: Optional[dict] = None) -> requests.Response:
    headers = {"Accept-Language": ACCEPT_LANGUAGE.get(lang, ACCEPT_LANGUAGE["en"])}
    last_error = None
    for attempt in range(2):
        try:
            response = SESSION.request(method, url, data=data, headers=headers,
                                       timeout=timeout, allow_redirects=True)
            if (response.status_code == 429 or response.status_code >= 500) and attempt == 0:
                time.sleep(1.2)
                continue
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.8)
    raise RuntimeError(str(last_error))

def unwrap_ddg_url(href: str) -> str:
    target = parse_qs(urlparse(urljoin("https://duckduckgo.com", href)).query).get("uddg")
    return target[0] if target else urljoin("https://duckduckgo.com", href)

def parse_ddg_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for node in soup.select("div.result, div.web-result"):
        if "result--ad" in node.get("class", []):
            continue
        anchor = node.select_one("a.result__a")
        if not anchor or not anchor.get("href"):
            continue
        url = unwrap_ddg_url(anchor["href"])
        if (urlparse(url).hostname or "").endswith("duckduckgo.com"):
            continue
        results.append({"title": squash(anchor.get_text(" ", strip=True)),
                        "url": url,
                        "snippet": squash((node.select_one(".result__snippet") or {}).get_text(" ", strip=True))})
    return results

def parse_ddg_lite(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    links, snippets = soup.select("a.result-link"), soup.select("td.result-snippet")
    out = []
    for i, anchor in enumerate(links):
        href = anchor.get("href")
        if not href:
            continue
        url = unwrap_ddg_url(href)
        if (urlparse(url).hostname or "").endswith("duckduckgo.com"):
            continue
        out.append({"title": squash(anchor.get_text(" ", strip=True)), "url": url,
                    "snippet": squash(snippets[i].get_text(" ", strip=True)) if i < len(snippets) else ""})
    return out

def ddg_search(query: str, *, max_results: int = 10,
               recency: Optional[str] = None, region: Optional[str] = None) -> list[dict]:
    """Search DuckDuckGo. recency may be d/day, w/week, m/month or y/year."""
    df = {"day": "d", "week": "w", "month": "m", "year": "y",
          "d": "d", "w": "w", "m": "m", "y": "y"}.get(recency)
    form = {"q": query}
    if df: form["df"] = df
    if region: form["kl"] = region
    headers = {"Content-Type": "application/x-www-form-urlencoded",
               "Referer": "https://duckduckgo.com/"}
    blocked = False
    results = []
    for endpoint, parser in (
        ("https://html.duckduckgo.com/html/", parse_ddg_html),
        ("https://lite.duckduckgo.com/lite/", parse_ddg_lite),
    ):
        try:
            r = SESSION.post(endpoint, data=form, headers=headers, timeout=20)
            blocked = blocked or r.status_code == 202 or "anomaly" in r.text.lower()
            if r.status_code == 200 and not blocked:
                results = parser(r.text)
            if results:
                break
        except requests.RequestException:
            pass
    if not results and blocked:
        raise RuntimeError("DuckDuckGo returned a bot-challenge page; retry later or reduce query frequency.")
    return results[:max_results]

def parse_feed(xml: str) -> list[dict]:
    """Parse RSS or Atom into title/link/description/date records."""
    root = ET.fromstring(xml)
    items = []
    for node in root.iter():
        if node.tag.split("}")[-1] not in ("item", "entry"):
            continue
        fields = {}
        for child in list(node):
            key = child.tag.split("}")[-1]
            fields.setdefault(key, child)
        title = squash("".join(fields["title"].itertext())) if "title" in fields else ""
        link_node = fields.get("link")
        link = ""
        if link_node is not None:
            link = link_node.attrib.get("href", "") or squash("".join(link_node.itertext()))
        if not link and "guid" in fields:
            link = squash("".join(fields["guid"].itertext()))
        desc_node = fields.get("description")
        if desc_node is None:
            desc_node = fields.get("summary")

        desc = (
            squash(BeautifulSoup("".join(desc_node.itertext()), "html.parser").get_text(" "))
            if desc_node is not None else ""
        )

        date_node = fields.get("pubDate")
        if date_node is None:
            date_node = fields.get("published")
        if date_node is None:
            date_node = fields.get("updated")

        date = squash("".join(date_node.itertext())) if date_node is not None else ""
        if title and link:
            items.append({"title": title, "link": link, "description": desc, "date": date or None})
    return items

def extract_listing_links(html: str, page_url: str, source: Source) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        canon = canonical_url(urljoin(page_url, href))
        if not canon or not source.is_article_url(canon):
            continue
        title = re.sub(r"\b\d+\s+(?:minutes?|hours?|days?)\s+ago\b.*$", "",
                       squash(anchor.get_text(" ", strip=True)), flags=re.I)
        if len(title) > len(found.get(canon, "")):
            found[canon] = title
        elif canon not in found:
            found[canon] = ""
    return [{"url": url, "title": title if len(title) >= 12 else title_from_slug(url)}
            for url, title in found.items()]

NOISE_SELECTOR = (
    "script, style, noscript, nav, aside, footer, form, iframe, figure, figcaption, "
    "button, svg, [aria-hidden='true'], .ad, .advert, .advertisement, .social, "
    ".share, .sharedaddy, .related, .newsletter, .comments"
)
BOILERPLATE = [
    re.compile(r"^(read also|also read|read more|related( stories| articles)?|soma pia|angalia pia|more on this story|share( this)?( article| story)?|follow us|sign up|subscribe( now| to our newsletter)?|stay informed|advertisement|audio by vocalize|listen to this article|ተጨማሪ ያንብቡ)\b", re.I),
    re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$"),
    re.compile(r"^(copyright|©)", re.I),
]

def clean_line(value: str) -> str:
    value = squash(value)
    if len(value) < 2 or any(rx.search(value) for rx in BOILERPLATE):
        return ""
    return value

def dedupe_blocks(blocks: list[str]) -> list[str]:
    out, seen = [], set()
    for block in blocks:
        if not block or block in seen:
            continue
        if out and len(block) > 20 and block in out[-1]:
            continue
        seen.add(block)
        out.append(block)
    return out

def _extract_blocks(nodes, remove_selectors: list[str]) -> list[str]:
    blocks = []
    for node in nodes:
        clone = BeautifulSoup(str(node), "html.parser")
        for element in clone.select(NOISE_SELECTOR):
            element.decompose()
        for selector in remove_selectors:
            try:
                for element in clone.select(selector):
                    element.decompose()
            except Exception:
                pass
        parts = clone.select("p, h2, h3, h4, blockquote, li")
        if parts:
            blocks.extend(clean_line(x.get_text(" ", strip=True)) for x in parts)
        else:
            blocks.append(clean_line(clone.get_text(" ", strip=True)))
    return dedupe_blocks(blocks)

def _json_ld_info(soup: BeautifulSoup) -> dict:
    info = {}
    def visit(obj):
        if isinstance(obj, list):
            for item in obj: visit(item)
        elif isinstance(obj, dict):
            if "@graph" in obj: visit(obj["@graph"])
            typ = obj.get("@type", "")
            typ = ",".join(typ) if isinstance(typ, list) else str(typ)
            if re.search(r"Article|NewsArticle|Reportage", typ, re.I):
                body = obj.get("articleBody")
                if isinstance(body, str) and len(body) > len(info.get("text", "")):
                    info["text"] = body
                info.setdefault("date", obj.get("datePublished"))
                info.setdefault("headline", obj.get("headline"))
                author = obj.get("author")
                if isinstance(author, list): author = author[0] if author else None
                if isinstance(author, dict): author = author.get("name")
                if isinstance(author, str): info.setdefault("author", author)
    for script in soup.select('script[type="application/ld+json"]'):
        try: visit(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError): pass
    return info

def extract_article(html: str, url: str, source: Source) -> Optional[dict]:
    soup = BeautifulSoup(html, "html.parser")
    ld = _json_ld_info(soup)
    title = (ld.get("headline") or
             (soup.select_one('meta[property="og:title"]') or {}).get("content") or
             (soup.select_one("h1") or {}).get_text(" ", strip=True) or
             (soup.title.get_text(" ", strip=True) if soup.title else ""))
    title = re.sub(r"\s*[|\-–—]\s*(BBC.*|Taifa Leo.*|The Standard.*|Standard Digital.*|Nation.*)$", "", squash(title), flags=re.I)
    date = (ld.get("date") or
            (soup.select_one('meta[property="article:published_time"]') or {}).get("content") or
            (soup.select_one('meta[name="pubdate"], meta[itemprop="datePublished"]') or {}).get("content") or
            (soup.select_one("time[datetime]") or {}).get("datetime"))
    author = ld.get("author") or (soup.select_one('meta[name="author"]') or {}).get("content")
    options = []
    for selector in source.content_selectors:
        try: nodes = soup.select(selector)
        except Exception: continue
        if not nodes: continue
        blocks = _extract_blocks(nodes, source.remove_selectors)
        options.append((f"selector: {selector}", blocks))
        if sum(map(len, blocks)) >= 800: break
    if not any(sum(map(len, b)) >= 800 for _, b in options) and ld.get("text"):
        text = BeautifulSoup(ld["text"], "html.parser").get_text("\n")
        blocks = dedupe_blocks([clean_line(x) for x in text.splitlines()])
        options.append(("json-ld", blocks if len(blocks) > 1 else [squash(ld["text"])]))
    if not any(sum(map(len, b)) >= 800 for _, b in options):
        try:
            readable = BeautifulSoup(Document(html).summary(), "html.parser")
            blocks = dedupe_blocks([clean_line(x.get_text(" ", strip=True))
                                    for x in readable.select("p, h2, h3, li, blockquote")])
            options.append(("readability", blocks))
            if not title:
                title = Document(html).short_title()
        except Exception:
            pass
    def broad(method): return method in ("selector: article", "selector: main")
    good = next(((m, b) for m, b in options
                 if sum(map(len, b)) >= 800 or (sum(map(len, b)) >= 350 and not broad(m))), None)
    pick = good or (max(options, key=lambda x: sum(map(len, x[1]))) if options else None)
    if not pick or sum(map(len, pick[1])) < 200:
        return None
    method, blocks = pick
    if blocks and title and blocks[0].lower() == title.lower():
        blocks = blocks[1:]
    return {"title": title or title_from_slug(url), "text": "\n\n".join(blocks),
            "publishedAt": date, "author": author, "method": method}

def recency_bonus(iso: Optional[str]) -> float:
    if not iso: return 0.0
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
        return 1.5 if days <= 2 else 0.5 if days <= 7 else 0.0
    except (ValueError, TypeError):
        return 0.0

def _cat_weight(candidate: dict, theme: str) -> int:
    weight = 0
    for cat in candidate["cats"]:
        for key, value in THEME_CATEGORIES[theme]:
            if key == cat: weight = max(weight, value)
    if theme in candidate["hints"]: weight = max(weight, 2)
    return weight

def relevance(candidate: dict, themes: Optional[list[str]], category: Optional[str], lang: str) -> tuple[int, Optional[str]]:
    hay = f'{candidate["title"]} {candidate["snippet"]} {slug_words(candidate["url"])}'.lower()
    if themes:
        best_score, best_theme = -1, None
        for theme in themes:
            hits = count_hits(hay, THEME_KEYWORDS[lang][theme])
            base = (1 if category in candidate["cats"] else 0) if category else _cat_weight(candidate, theme)
            score = base + 2 * min(3, hits)
            if score > best_score: best_score, best_theme = score, theme
        return best_score, best_theme
    if category:
        hits = count_hits(hay, CATEGORY_KEYWORDS[lang].get(category, []))
        return (3 if category in candidate["cats"] else 0) + 2 * min(3, hits), None
    return 3, None

def _add_candidate(mapping: dict, url: str, title: str, snippet: str,
                   source: Source, origin: str, cat: Optional[str] = None,
                   hint: Optional[str] = None, published_at: Optional[str] = None):
    canon = canonical_url(url)
    if not canon: return
    if canon in mapping:
        old = mapping[canon]
        if cat: old["cats"].add(cat)
        if hint: old["hints"].add(hint)
        if len(title) > len(old["title"]) and not title.startswith("http"): old["title"] = title
        if not old["snippet"] and snippet: old["snippet"] = snippet
        if not old.get("publishedAt") and published_at: old["publishedAt"] = published_at
        return
    mapping[canon] = {"url": canon, "title": title, "snippet": snippet,
                      "publishedAt": published_at, "source": source,
                      "cats": {cat} if cat else set(), "hints": {hint} if hint else set(),
                      "origin": origin}

def _categories_for(themes: Optional[list[str]], category: Optional[str]) -> list[str]:
    if category: return [category]
    out = set()
    for theme in themes or []:
        for cat, weight in THEME_CATEGORIES[theme]:
            if weight > 0 or cat == "local": out.add(cat)
    return list(out)

def _build_seeds(source: Source, cats: list[str], region: Optional[dict]) -> list[dict]:
    seeds, seen = [], set()
    def push(url, kind, cat):
        if url not in seen:
            seen.add(url); seeds.append({"url": url, "kind": kind, "cat": cat})
    for cat in list(dict.fromkeys(cats + ["general"])):
        for page in source.pages.get(cat, []): push(urljoin(source.base, page), "page", cat)
        for feed in source.feeds.get(cat, []): push(feed, "rss", cat)
    if source.id == "bbc_en" and region and region.get("key") in AFRICAN_REGION_KEYS:
        for feed in source.feeds.get("local", []): push(feed, "rss", "local")
    return seeds[:12]

def _pick_sources(lang: str, region: Optional[dict], ids: Optional[list[str]]) -> list[Source]:
    result = [s for s in SOURCES if s.lang == lang]
    if ids: result = [s for s in result if s.id in ids]
    if lang == "en" and region and region.get("key") not in (None, "kenya", "east africa"):
        result.sort(key=lambda s: 0 if s.id == "bbc_en" else 1)
    return result

def _discover(lang: str, region: Optional[dict], themes: Optional[list[str]],
              category: Optional[str], sources: list[Source], progress: Callable):
    candidates, warnings = {}, []
    jobs = [(source, seed) for source in sources
            for seed in _build_seeds(source, _categories_for(themes, category), region)]
    progress(f"Reading {len(jobs)} section pages and feeds from {', '.join(s.name for s in sources)}…")
    for source, seed in jobs:
        try:
            response = fetch_page(seed["url"], lang=source.lang, timeout=15)
            if seed["kind"] == "rss":
                for item in parse_feed(response.text):
                    canon = canonical_url(item["link"])
                    if canon and source.is_article_url(canon):
                        published = item.get("date")
                        _add_candidate(candidates, canon, item["title"], item["description"],
                                       source, "rss", seed["cat"], published_at=published)
            else:
                for item in extract_listing_links(response.text, response.url, source):
                    _add_candidate(candidates, item["url"], item["title"], "", source, "page", seed["cat"])
        except Exception as exc:
            logger.debug("Could not read %s: %s", seed["url"], exc)
    for source in sources:
        if not any(c["source"].id == source.id for c in candidates.values()):
            warnings.append(f"{source.name}: no articles discovered from section pages/feeds; relying on search.")
    return candidates, warnings

def _supplement_search(lang: str, region: Optional[dict], themes: Optional[list[str]],
                       category: Optional[str], query: Optional[str], sources: list[Source],
                       candidates: dict, warnings: list[str], progress: Callable):
    themes_to_search = themes or [None]
    jobs = []
    for source in sources:
        for theme in themes_to_search:
            kws = THEME_KEYWORDS[lang][theme] if theme else CATEGORY_KEYWORDS[lang].get(category or "general", [])
            have = sum(1 for c in candidates.values()
                       if c["source"].id == source.id and
                       (theme is None or relevance(c, [theme], category, lang)[0] >= 2))
            jobs.append((have, source, theme, kws))
    jobs.sort(key=lambda x: x[0])
    for _, source, theme, kws in jobs[:4]:
        kw = " OR ".join(f'"{k.strip()}"' if " " in k else k.strip() for k in kws[:4])
        parts = [f"site:{source.search_scope}", query, f"({kw})" if kw else "",
                 region["label"] if region else ""]
        q = " ".join(x for x in parts if x)
        try:
            progress(f"Searching DuckDuckGo: {q}")
            for hit in ddg_search(q, max_results=10, recency="month"):
                canon = canonical_url(hit["url"])
                if canon and source.is_article_url(canon):
                    _add_candidate(candidates, canon, hit["title"], hit["snippet"],
                                   source, "search", hint=theme)
        except Exception as exc:
            warnings.append(f"DuckDuckGo query failed ({exc})")
            break
        time.sleep(0.8)

def _select_balanced(scored: list[dict], themes: Optional[list[str]], n: int) -> list[dict]:
    ordered = sorted(scored, key=lambda x: x["score"], reverse=True)
    if not themes or len(themes) < 2: return ordered[:n]
    buckets = {}
    for item in ordered: buckets.setdefault(item.get("theme") or "none", []).append(item)
    picked, keys, round_no = [], list(buckets), 0
    while len(picked) < n:
        added = False
        for key in keys:
            if round_no < len(buckets[key]) and len(picked) < n:
                picked.append(buckets[key][round_no]); added = True
        if not added: break
        round_no += 1
    return picked

def _truncate_at_paragraph(text: str, maximum: int) -> str:
    if len(text) <= maximum: return text
    cut = text[:maximum]
    idx = cut.rfind("\n\n")
    base = cut[:idx] if idx > maximum * 0.6 else re.sub(r"\s+\S*$", "", cut)
    return base + " […]"

def fetch_news_context(
    language: str,
    region: Optional[str] = None,
    theme: Optional[str] = None,
    category: Optional[str] = None,
    query: Optional[str] = None,
    max_articles: int = 6,
    max_chars_per_article: int = 8000,
    max_total_chars: int = 40000,
    strict_region: bool = False,
    sources: Optional[list[str]] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Gather recent full-text articles for a language, region and theme/category.

    language: en, sw or am
    theme: work, travel, school, shopping, family or daily_planning
    category: newsroom category such as politics, sports, health or business
    query: optional phrase used to discover and rank matching articles
    sources: optional source IDs (taifaleo, standard, bbc_sw, bbc_am, bbc_en)
    """
    lang = normalize_lang(language)
    if not lang:
        raise ValueError(f'Unsupported language "{language}". Use en, sw or am.')
    if theme is not None and theme not in THEMES:
        raise ValueError(f"Unsupported theme {theme!r}; choose from {', '.join(THEMES)}.")
    if category is not None and category not in CATEGORIES:
        raise ValueError(f"Unsupported category {category!r}.")
    if not 1 <= max_articles <= 15: raise ValueError("max_articles must be between 1 and 15.")
    if not 1000 <= max_chars_per_article <= 20000: raise ValueError("max_chars_per_article must be 1000-20000.")
    if not 5000 <= max_total_chars <= 120000: raise ValueError("max_total_chars must be 5000-120000.")
    progress = progress or (lambda message: None)
    region_info = resolve_region(region)
    mode_themes = [theme] if theme else (None if category else list(THEMES))
    selected_sources = _pick_sources(lang, region_info, sources)
    if not selected_sources:
        raise ValueError(f"No sources configured for language {lang!r}.")
    candidates, warnings = _discover(lang, region_info, mode_themes, category, selected_sources, progress)

    relevant_count = sum(1 for c in candidates.values()
                         if relevance(c, mode_themes, category, lang)[0] >= 2)
    if relevant_count < max_articles * 2 or query:
        _supplement_search(lang, region_info, mode_themes, category, query,
                           selected_sources, candidates, warnings, progress)

    scored = []
    for candidate in candidates.values():
        rel_score, rel_theme = relevance(candidate, mode_themes, category, lang)
        if rel_score < 2: continue
        score = rel_score + recency_bonus(candidate.get("publishedAt"))
        hay = f'{candidate["title"]} {candidate["snippet"]} {slug_words(candidate["url"])}'
        if query:
            score += 2 * count_hits(hay.lower(), [w for w in query.lower().split() if len(w) > 2])
        if region_info:
            score += min(2, count_occurrences(
                f'{candidate["title"]} {candidate["snippet"]}'.lower(), region_info["terms"]))
        scored.append({"c": candidate, "score": score, "theme": rel_theme})
    if not scored:
        text = f"No relevant {LANG_NAMES[lang]} articles found."
        if warnings: text += "\n" + "\n".join(f"- {w}" for w in warnings)
        return {"text": text, "details": {"articles": [], "warnings": warnings}}

    to_fetch = _select_balanced(scored, mode_themes, min(40, int(max_articles * 1.8 + 0.999)))
    progress(f"Downloading {len(to_fetch)} candidate articles…")
    extracted, skipped = [], []
    for item in to_fetch:
        candidate = item["c"]
        try:
            response = fetch_page(candidate["url"], lang=candidate["source"].lang)
            article = extract_article(response.text, response.url, candidate["source"])

            if not article:
                print(f"Skipped: {candidate['url']} — no article body found")
                skipped.append({
                    "url": candidate["url"],
                    "reason": "no article body found (paywall, video page, or markup changed)"
                })
                continue

            print(f"Extracted: {article['title']} ({len(article['text'])} characters)")
            
            if not article:
                skipped.append({"url": candidate["url"], "reason": "no article body found (paywall, video page, or markup changed)"})
                continue
            if len(article["text"]) < 600:
                skipped.append({"url": candidate["url"], "reason": f'too short ({len(article["text"])} chars; likely paywalled or a brief)'})
                continue
            score, chosen_theme = item["score"], item["theme"]
            body_lower = article["text"].lower()
            if mode_themes:
                best_hits = -1
                for t in mode_themes:
                    hits = count_hits(body_lower, THEME_KEYWORDS[lang][t])
                    if hits > best_hits:
                        best_hits = hits
                        if hits >= 2: chosen_theme = t
                score += min(8, best_hits)
            elif category:
                score += min(8, count_hits(body_lower, CATEGORY_KEYWORDS[lang].get(category, [])))
            if region_info:
                mentions = count_occurrences(body_lower, region_info["terms"])
                if strict_region and mentions == 0:
                    skipped.append({"url": candidate["url"], "reason": f'no mention of region "{region_info["label"]}"'})
                    continue
                score += min(4, mentions)
            score += recency_bonus(article.get("publishedAt") or candidate.get("publishedAt"))
            extracted.append({"c": candidate, "score": score, "theme": chosen_theme, "art": article})
        except Exception as exc:
            skipped.append({"url": candidate["url"], "reason": str(exc)})

    ranked = _select_balanced(extracted, mode_themes, max_articles)
    output_articles, parts, used = [], [], 0
    for item in ranked:
        remaining = max_total_chars - used
        if remaining < 1500: break
        c, art = item["c"], item["art"]
        body = _truncate_at_paragraph(art["text"], min(max_chars_per_article, remaining - 400))
        date = (art.get("publishedAt") or c.get("publishedAt") or "")[:10]
        theme_name = item.get("theme") or category or "general"
        header = [
            f'## [{len(output_articles) + 1}] {art["title"]}',
            f'Source: {c["source"].name} | Theme: {theme_name}'
            + (f" | Published: {date}" if date else "")
            + (f' | By: {art["author"]}' if art.get("author") else ""),
            f'URL: {c["url"]}',
        ]
        block = "\n".join(header) + "\n\n" + body
        parts.append(block)
        used += len(block)
        output_articles.append({
            "title": art["title"], "url": c["url"], "source": c["source"].name,
            "theme": item.get("theme"), "category": category,
            "publishedAt": art.get("publishedAt") or c.get("publishedAt"),
            "author": art.get("author"), "chars": len(body),
            "method": art["method"], "score": round(item["score"], 1),
        })
    theme_desc = f"themes: {', '.join(mode_themes)}" if mode_themes else f"category: {category}"
    source_names = ", ".join(dict.fromkeys(a["source"] for a in output_articles)) or "n/a"
    head = (f"# News context — {LANG_NAMES[lang]}"
            + (f" | region: {region_info['label']}" if region_info else "")
            + f" | {theme_desc}\nCollected {len(output_articles)} full articles "
            + f"({used:,} characters) on {datetime.now(timezone.utc).date().isoformat()} from: {source_names}."
            + (("\nNotes:\n" + "\n".join(f"- {w}" for w in warnings)) if warnings else ""))
    return {
        "text": head + "\n\n---\n\n" + "\n\n---\n\n".join(parts),
        "details": {"articles": output_articles, "skipped": skipped,
                    "warnings": warnings, "candidatesConsidered": len(candidates)},
    }

def news_context():
    """Small command-line interface for manual testing."""
    import argparse
    parser = argparse.ArgumentParser(description="Fetch full-text news context.")
    parser.add_argument("--language", required=True, choices=("en", "sw", "am"))
    parser.add_argument("--region")
    parser.add_argument("--theme", choices=THEMES)
    parser.add_argument("--category", choices=CATEGORIES)
    parser.add_argument("--query")
    parser.add_argument("--max-articles", type=int, default=1)
    parser.add_argument("--strict-region", action="store_true")
    args = parser.parse_args()
    result = fetch_news_context(
        language=args.language, region=args.region, theme=args.theme,
        category=args.category, query=args.query,
        max_articles=args.max_articles, strict_region=args.strict_region,
        progress=print,
    )
    return result["text"]

if __name__ == "__main__":
    print(news_context())
