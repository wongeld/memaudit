import asyncio
import json
import math
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mcp.server import MCPServer

NOMINATIM_URL = os.environ.get(
    "NOMINATIM_URL",
    "http://localhost:8080",
).rstrip("/")
USER_AGENT = os.environ.get(
    "OPENSTREETMAP_MCP_USER_AGENT",
    "profile-generation-openstreetmap-mcp/0.1",
)
ATTRIBUTION = "© OpenStreetMap contributors (https://www.openstreetmap.org/copyright)"
REQUEST_INTERVAL_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 20

server = MCPServer(
    "openstreetmap",
    instructions=(
        "Search and reverse-geocode individual user-requested places using a "
        "Nominatim-compatible service. Configure NOMINATIM_URL to a service you "
        "are authorized to use; the default is a local service. Do not submit "
        "personal or confidential data, use autocomplete, or make bulk/systematic "
        "queries. Requests are limited to at most one per second. Attribute map "
        "data to OpenStreetMap contributors. Public Nominatim usage policy: "
        "https://operations.osmfoundation.org/policies/nominatim/"
    ),
)
request_lock = asyncio.Lock()
last_request_time = 0.0


def fetch_json(url: str) -> Any:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RuntimeError(f"Nominatim returned HTTP {error.code}.") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach Nominatim: {error.reason}") from error


async def nominatim_request(endpoint: str, parameters: dict[str, str]) -> Any:
    global last_request_time

    url = f"{NOMINATIM_URL}/{endpoint}?{urlencode(parameters)}"
    async with request_lock:
        delay = REQUEST_INTERVAL_SECONDS - (time.monotonic() - last_request_time)
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            return await asyncio.to_thread(fetch_json, url)
        finally:
            last_request_time = time.monotonic()


def format_osm_url(place: dict[str, Any]) -> str | None:
    osm_type = place.get("osm_type")
    osm_id = place.get("osm_id")
    if osm_type not in {"node", "way", "relation"} or osm_id is None:
        return None
    return f"https://www.openstreetmap.org/{osm_type}/{osm_id}"


@server.tool()
async def search_places(query: str, limit: int = 5) -> str:
    """Find an individual place by name or address; do not use for autocomplete or bulk searches."""
    normalized_query = query.strip()
    if not normalized_query or len(normalized_query) > 200:
        raise ValueError("Query must contain between 1 and 200 characters.")
    if not 1 <= limit <= 10:
        raise ValueError("Limit must be between 1 and 10.")

    results = await nominatim_request(
        "search",
        {
            "q": normalized_query,
            "format": "jsonv2",
            "addressdetails": "1",
            "limit": str(limit),
        },
    )
    if not isinstance(results, list):
        raise RuntimeError("Nominatim returned an unexpected search response.")

    places = [
        {
            "name": place.get("name") or place.get("display_name"),
            "display_name": place.get("display_name"),
            "latitude": place.get("lat"),
            "longitude": place.get("lon"),
            "category": place.get("category"),
            "type": place.get("type"),
            "address": place.get("address"),
            "osm_url": format_osm_url(place),
        }
        for place in results
        if isinstance(place, dict)
    ]
    return json.dumps(
        {"attribution": ATTRIBUTION, "results": places},
        ensure_ascii=False,
    )


@server.tool()
async def reverse_geocode(latitude: float, longitude: float) -> str:
    """Find the address for one user-requested coordinate; do not use for systematic lookups."""
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90.")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180.")

    result = await nominatim_request(
        "reverse",
        {
            "lat": str(latitude),
            "lon": str(longitude),
            "format": "jsonv2",
            "addressdetails": "1",
        },
    )
    if not isinstance(result, dict):
        raise RuntimeError("Nominatim returned an unexpected reverse-geocode response.")

    place = {
        "name": result.get("name") or result.get("display_name"),
        "display_name": result.get("display_name"),
        "latitude": result.get("lat"),
        "longitude": result.get("lon"),
        "address": result.get("address"),
        "osm_url": format_osm_url(result),
    }
    return json.dumps(
        {"attribution": ATTRIBUTION, "result": place},
        ensure_ascii=False,
    )


if __name__ == "__main__":
    asyncio.run(server.run_stdio_async())
