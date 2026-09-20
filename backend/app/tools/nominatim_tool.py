"""Real place search + geocoding via OpenStreetMap Nominatim.

Free, no API key. Resolves (and searches for) anything Nominatim knows about:
a neighborhood, a specific address, a building, any mapped point of interest.

Nominatim's usage policy (https://operations.osmfoundation.org/policies/nominatim/)
requires a descriptive User-Agent and roughly 1 request/second, and asks
that real projects not lean on the free public instance for heavy traffic.
This project's usage — a handful of interactive searches per session — fits
that; `_RateLimiter` enforces the request spacing in-process. A deployment
with real traffic should move to a paid provider or a self-hosted instance.

Resolving a real place is only half the story: without `TAVILY_API_KEY` set
too, nothing is searched and the response says so. Geocoding answers "where is
this," not "what does the web say about it" — see `backend/README.md`.
"""

from __future__ import annotations

import re
import time

import httpx

from app.models.location import Location
from app.models.place import PlaceCandidate
from app.tools.base import LocationNotFoundError, LocationResolverTool, ToolExecutionError

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
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

    def search(self, query: str, limit: int, country_code: str | None = None) -> list[dict]:
        self._rate_limiter.wait()
        # accept-language=en: names and addresses come back in English wherever
        # OpenStreetMap has an English name ("Chuo", not "中央区"), so a place
        # in Japan or Germany is readable without the user knowing the language.
        params: dict[str, object] = {
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": limit,
            "accept-language": "en",
        }
        if country_code:
            params["countrycodes"] = country_code
        try:
            response = self._client.get(_NOMINATIM_URL, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Nominatim search failed for '{query}': {exc}") from exc
        return response.json()


    def reverse(self, latitude: float, longitude: float, language: str = "en", zoom: int = 14) -> dict:
        """The address of a coordinate, with names in `language` where OpenStreetMap has them."""
        self._rate_limiter.wait()
        params = {
            "lat": latitude,
            "lon": longitude,
            "format": "jsonv2",
            "addressdetails": 1,
            "zoom": zoom,
            "accept-language": language,
        }
        try:
            response = self._client.get(_NOMINATIM_REVERSE_URL, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Nominatim reverse lookup failed for {latitude},{longitude}: {exc}") from exc
        return response.json()


_US_STATE_ABBREVIATIONS = frozenset(
    """AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ
    NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC""".split()
)
_US_STATE_NAMES = frozenset(
    {
        "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
        "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa",
        "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
        "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire",
        "new jersey", "new mexico", "new york", "north carolina", "north dakota", "ohio",
        "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota",
        "tennessee", "texas", "utah", "vermont", "virginia", "washington", "west virginia",
        "wisconsin", "wyoming", "district of columbia",
    }
)
_US_COUNTRY_NAMES = frozenset({"us", "usa", "u.s.", "u.s.a.", "united states", "united states of america"})
_TRAILING_ZIP_RE = re.compile(r"\s*\d{5}(?:-\d{4})?$")


def _detect_country_code(query: str) -> str | None:
    """Constrain the search to a country when the query names a US state.

    Without this, a business name that is also a country name hijacks the
    geocode entirely: "Venezuela, Boston, MA" resolves to a street in
    Venezuela the country, because Nominatim matched the strongest token and
    dropped the rest. Naming a US state is a strong, explicit signal from the
    user about which country they mean.

    Deliberately US-only, and deliberately narrow about *where* in the query
    it looks: only the trailing comma-separated segments (where a state
    actually sits: "Boston, MA 02122", "Cambridge MA"), and abbreviations must
    be uppercase. Scanning every word was a real bug — "hotel in Tokyo" read
    "in" as Indiana and returned New York hotels, and "me", "or", "la", "id"
    are all common words that are also state codes. A query with no
    recognizable US state at the end is left unconstrained rather than guessed at.
    """
    segments = [segment.strip() for segment in query.split(",") if segment.strip()]
    for segment in segments[-2:]:
        segment = _TRAILING_ZIP_RE.sub("", segment).strip()
        lowered = segment.lower()
        if lowered in _US_COUNTRY_NAMES or lowered in _US_STATE_NAMES:
            return "us"
        words = segment.split()
        if words and words[-1] in _US_STATE_ABBREVIATIONS:
            return "us"
        if any(lowered.endswith(f" {name}") for name in _US_STATE_NAMES):
            return "us"
    return None


def _query_variants(query: str) -> list[str]:
    """Progressively broader ways to ask about one free-text place.

    OSM knows addresses far more completely than it knows business names, so
    "Venezuela, 20 Ericsson St, Boston, MA 02122" returns nothing while the
    address alone resolves exactly. Dropping leading comma-separated segments
    turns the first into the second. Later segments are never dropped — those
    carry the geography, which is the part that must stay.
    """
    cleaned = query.strip()
    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    variants = [cleaned]
    for dropped in range(1, min(len(parts), 3)):
        remainder = ", ".join(parts[dropped:])
        if len(remainder) > 4 and remainder not in variants:
            variants.append(remainder)
    return variants


def _leading_name(query: str, variant: str) -> str | None:
    """The part of the user's query a fallback variant dropped — normally the
    business name. Worth keeping for display: geocoding the address yields a
    house number as its name, and showing "20" where the user typed
    "Venezuela" would look broken even though the coordinates are right."""
    if variant == query.strip():
        return None
    dropped = query.strip().removesuffix(variant).strip().rstrip(",").strip()
    return dropped or None


def _search_with_fallback(
    client: NominatimClient, query: str, limit: int
) -> tuple[list[dict], str | None]:
    """Walk the variant ladder until something resolves.

    Returns the results plus whatever leading segment had to be dropped to
    get them, so callers can keep showing the name the user actually typed.
    """
    country_code = _detect_country_code(query)
    for variant in _query_variants(query):
        results = client.search(variant, limit, country_code=country_code)
        if results:
            return results, _leading_name(query, variant)
    return [], None


def _address_field(address: dict, *keys: str) -> str | None:
    for key in keys:
        if address.get(key):
            return address[key]
    return None


# OSM classes that mean "one specific venue" rather than an area, road or
# address: a cafe or hotel is a business, a neighbourhood or a house number isn't.
_BUSINESS_CLASSES = frozenset({"amenity", "shop", "tourism", "leisure", "office", "craft", "healthcare"})


# Within those classes, these are places rather than a business people review: a park is
# `leisure=park`, a viewpoint or monument is `tourism=...`, a mosque is `amenity=place_of_worship`.
_NOT_A_BUSINESS_TYPES = frozenset(
    {
        "park", "garden", "nature_reserve", "playground", "pitch", "common", "attraction", "viewpoint",
        "artwork", "information", "picnic_site", "camp_site", "place_of_worship", "grave_yard", "toilets",
        "bench", "parking", "bicycle_parking", "fountain", "shelter", "drinking_water", "school",
        "university", "college", "kindergarten", "townhall", "police", "fire_station",
    }
)


def _is_business(result: dict) -> bool:
    # jsonv2 (what we request) calls it "category"; the older json format
    # called the same thing "class". Checking only one silently classified
    # nothing as a business.
    if (result.get("category") or result.get("class")) not in _BUSINESS_CLASSES:
        return False
    return result.get("type") not in _NOT_A_BUSINESS_TYPES


# What Nominatim calls a single building or house: an address, not a named place.
_ADDRESS_TYPES = frozenset({"house", "building", "apartments", "detached", "terrace", "semidetached_house", "yes"})


def _is_address(result: dict) -> bool:
    if _is_business(result):
        return False
    return result.get("category") == "building" or result.get("addresstype") in {"house", "building"} or (
        result.get("type") in _ADDRESS_TYPES and result.get("category") in {"building", "place"}
    )


def _region_of(result: dict, city: str | None) -> str | None:
    """The state/prefecture/province a result is in.

    Nominatim's structured `state` is missing for many non-US places — a
    Tokyo address carries only "Chuo" and an ISO code — yet the region is right
    there in the display name ("..., Chuo, Tokyo, 104-0045, Japan"). Without
    it, downstream searches anchor on a bare ward name like "Chuo", which
    matches a university and a train line before it matches the place.
    """
    address = result.get("address", {})
    region = _address_field(address, "state", "region", "province", "state_district")
    if region or not city:
        return region

    parts = [part.strip() for part in result.get("display_name", "").split(",")]
    country = address.get("country")
    if city in parts:
        following = parts[parts.index(city) + 1 :]
        for part in following:
            if part and part != country and not any(ch.isdigit() for ch in part):
                return part
            break
    return None


def _result_to_location(result: dict, raw_query: str) -> Location:
    address = result.get("address", {})
    name = result.get("name") or result.get("display_name", "").split(",")[0]
    city = _address_field(address, "city", "town", "village", "suburb")
    region = _region_of(result, city)
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
        is_business=_is_business(result),
        is_address=_is_address(result),
    )


def _result_to_candidate(result: dict) -> PlaceCandidate:
    address = result.get("address", {})
    name = result.get("name") or result.get("display_name", "").split(",")[0]
    city = _address_field(address, "city", "town", "village", "suburb")
    return PlaceCandidate(
        name=name,
        display_name=result.get("display_name", name),
        category=result.get("type") or result.get("class") or "place",
        city=city,
        region=_region_of(result, city),
        country=address.get("country"),
        latitude=float(result["lat"]),
        longitude=float(result["lon"]),
        is_business=_is_business(result),
        is_address=_is_address(result),
    )


class NominatimLocationResolverTool(LocationResolverTool):
    """Resolves any real place — an address, a specific business — via live
    geocoding, not just the two hardcoded demo neighborhoods."""

    def __init__(self, client: NominatimClient | None = None) -> None:
        self._client = client or NominatimClient()

    def resolve(self, raw_query: str) -> Location:
        results, dropped_name = _search_with_fallback(self._client, raw_query, limit=1)
        if not results:
            raise LocationNotFoundError(f"Could not resolve location: {raw_query!r}")
        location = _result_to_location(results[0], raw_query)
        if dropped_name:
            # Geocoded via the address after the business name was dropped —
            # keep the name the user typed rather than the house number.
            location = location.model_copy(update={"name": dropped_name})
        return location


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
        results, dropped_name = _search_with_fallback(self._client, query, limit)
        candidates = [_result_to_candidate(r) for r in results]
        if dropped_name:
            candidates = [c.model_copy(update={"name": dropped_name}) for c in candidates]
        return candidates
