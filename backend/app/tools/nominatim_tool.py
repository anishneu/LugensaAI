"""Real place search + geocoding via OpenStreetMap Nominatim.

Free, no API key — the missing piece that let location resolution mean only
"one of two hardcoded demo neighborhoods." `FixtureLocationResolver` still
handles those two instantly and deterministically; this resolves (and
searches for) anything else Nominatim knows about — a specific Starbucks
address, a specific building, any real point of interest — not just a
neighborhood.

Nominatim's usage policy (https://operations.osmfoundation.org/policies/nominatim/)
requires a descriptive User-Agent and roughly 1 request/second, and asks
that real projects not lean on the free public instance for heavy traffic.
This project's usage — a handful of interactive searches per session — fits
that; `_RateLimiter` enforces the request spacing in-process. A deployment
with real traffic should move to a paid provider or a self-hosted instance.

Resolving a real place is only half the story: without `TAVILY_API_KEY` set
too, `FixtureWebSearchTool` has no fixture files for a place outside the two
demo neighborhoods and will honestly return zero evidence for it. Geocoding
answers "where is this," not "what does the web say about it" — see
`backend/README.md`.
"""

from __future__ import annotations

import re
import time

import httpx

from app.models.location import Location
from app.models.place import PlaceCandidate
from app.tools.base import LocationNotFoundError, LocationResolverTool, ToolExecutionError

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "LugensaAI-LocationResearchAgent/0.1 (educational demo project; not for production traffic)"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "place"


class _RateLimiter:
    """Process-wide throttle honoring Nominatim's ~1 request/second policy."""

    def __init__(self, min_interval_seconds: float = 1.0) -> None:
        self._min_interval = min_interval_seconds
        self._last_request_at = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_at = time.monotonic()


class NominatimClient:
    """Thin wrapper around the Nominatim HTTP API.

    `transport` is exposed purely so tests can inject `httpx.MockTransport`
    instead of making a real network call — see `tests/test_nominatim_tool.py`.
    """

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(transport=transport, timeout=10.0, headers={"User-Agent": _USER_AGENT})
        self._rate_limiter = _RateLimiter()

    def search(self, query: str, limit: int) -> list[dict]:
        self._rate_limiter.wait()
        try:
            response = self._client.get(
                _NOMINATIM_URL,
                params={"q": query, "format": "jsonv2", "addressdetails": 1, "limit": limit},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Nominatim search failed for '{query}': {exc}") from exc
        return response.json()


def _address_field(address: dict, *keys: str) -> str | None:
    for key in keys:
        if address.get(key):
            return address[key]
    return None


def _result_to_location(result: dict, raw_query: str) -> Location:
    address = result.get("address", {})
    name = result.get("name") or result.get("display_name", "").split(",")[0]
    city = _address_field(address, "city", "town", "village", "suburb")
    region = _address_field(address, "state", "region")
    country = address.get("country")
    slug = slugify(f"{name}-{city or ''}-{region or ''}-{result.get('osm_id', '')}")
    return Location(
        name=name,
        city=city,
        region=region,
        country=country,
        slug=slug,
        latitude=float(result["lat"]),
        longitude=float(result["lon"]),
        raw_query=raw_query,
    )


def _result_to_candidate(result: dict) -> PlaceCandidate:
    address = result.get("address", {})
    name = result.get("name") or result.get("display_name", "").split(",")[0]
    return PlaceCandidate(
        name=name,
        display_name=result.get("display_name", name),
        category=result.get("type") or result.get("class") or "place",
        city=_address_field(address, "city", "town", "village", "suburb"),
        region=_address_field(address, "state", "region"),
        country=address.get("country"),
        latitude=float(result["lat"]),
        longitude=float(result["lon"]),
    )


class NominatimLocationResolverTool(LocationResolverTool):
    """Resolves any real place — an address, a specific business — via live
    geocoding, not just the two hardcoded demo neighborhoods."""

    def __init__(self, client: NominatimClient | None = None) -> None:
        self._client = client or NominatimClient()

    def resolve(self, raw_query: str) -> Location:
        results = self._client.search(raw_query, limit=1)
        if not results:
            raise LocationNotFoundError(f"Could not resolve location: {raw_query!r}")
        return _result_to_location(results[0], raw_query)


class NominatimPlaceSearchTool:
    """Returns several real candidates for autocomplete instead of
    committing to one — e.g. every Starbucks Nominatim knows near a query.

    Deliberately not a `LocationResolverTool` — that interface resolves to
    exactly one `Location`; this is the "let the user pick which one" step
    that runs before resolution.
    """

    def __init__(self, client: NominatimClient | None = None) -> None:
        self._client = client or NominatimClient()

    def search_places(self, query: str, limit: int = 6) -> list[PlaceCandidate]:
        if not query.strip():
            return []
        results = self._client.search(query, limit)
        return [_result_to_candidate(r) for r in results]
