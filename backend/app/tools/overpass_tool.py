"""Nearby amenities from OpenStreetMap via the free Overpass API.

This is the project's answer to "why not just use Google Maps for the hard
facts?": Google's Places API needs a billing account and scraping Maps breaks
its terms, whereas OSM is free, global, and — used this way — deterministic.
"What's around this exact pin" is answered from map features with computed
distances rather than an LLM summarizing web pages about it, so a bar, a
station, or a pharmacy is listed only if it exists in the map data.

What OSM does *not* have is ratings, reviews, or live opening status; those
remain web-evidence-derived elsewhere in the app and are labeled as such.
"""

from __future__ import annotations

import math
import threading
import time

import httpx

from app.models.nearby import NearbyGroup, NearbyItem, NearbyPlaces
from app.tools.base import ToolExecutionError

# The public servers shed load with 429/504 often, and a dense city centre makes the query heavy: for
# Manchester the main server answered in 3 s one minute and returned 504 after 12 s the next, one mirror
# needed 24 s, and an earlier 15 s timeout for every attempt turned that into "no map data" although the data
# was there. So: several servers (the main one's two official alternates answer independently of it, plus two
# unrelated mirrors), a timeout per attempt that grows for the slower mirrors, one last retry of the first
# server after a pause, and the last good answer for that spot when every one of them fails.
# Two mirrors that were once popular (overpass.openstreetmap.fr, maps.mail.ru) now refuse or time out for
# this query, and overpass.osm.jp and overpass.openstreetmap.ie were unreachable when tried: all dropped.
# How far around the pin "Around this pin" looks. It was 600 m; 1 km covers what a visitor would walk to. The area, and
# so the work the public servers do, is nearly three times as large, which the per-attempt timeouts below allow for.
NEARBY_RADIUS_M = 1000

_OVERPASS_ATTEMPTS: tuple[tuple[str, float], ...] = (
    ("https://lz4.overpass-api.de/api/interpreter", 12.0),
    ("https://overpass-api.de/api/interpreter", 12.0),
    ("https://z.overpass-api.de/api/interpreter", 12.0),
    ("https://overpass.kumi.systems/api/interpreter", 20.0),
    ("https://overpass.private.coffee/api/interpreter", 30.0),
)
_RETRY_FIRST_AFTER_SECONDS = 2.0
_CACHE_TTL_SECONDS = 60 * 60
# Map data changes slowly. When every server fails, an answer up to a day old beats an empty card.
_STALE_OK_SECONDS = 24 * 60 * 60
_CACHE: dict[tuple[float, float, int], tuple[float, NearbyPlaces]] = {}
_CACHE_LOCK = threading.Lock()
_USER_AGENT = "LugensaAI/1.0 (location research demo)"

# group label -> (OSM tag key, accepted values, display kind per value or None to reuse the value)
_GROUPS: list[tuple[str, str, dict[str, str]]] = [
    ("Food & drink", "amenity", {"restaurant": "restaurant", "cafe": "cafe", "fast_food": "fast food", "bar": "bar", "pub": "pub"}),
    ("Transit", "railway", {"station": "train station", "subway_entrance": "subway entrance", "tram_stop": "tram stop"}),
    ("Transit", "highway", {"bus_stop": "bus stop"}),
    ("Groceries & convenience", "shop", {"supermarket": "supermarket", "convenience": "convenience store"}),
    ("Health", "amenity", {"pharmacy": "pharmacy", "hospital": "hospital", "clinic": "clinic"}),
    ("Safety", "amenity", {"police": "police station"}),
    ("Money", "amenity", {"bank": "bank", "atm": "ATM"}),
]
# Enough for a full list in the UI's detail view; the card itself shows only the first few.
_MAX_LISTED_PER_GROUP = 15


def _query(lat: float, lon: float, radius_m: int) -> str:
    clauses = []
    for _, key, values in _GROUPS:
        pattern = "|".join(values)
        clauses.append(f'  nwr(around:{radius_m},{lat},{lon})["{key}"~"^({pattern})$"];')
    # No `out center N` cap: in a dense centre the first N elements are not the nearest N, and the closest
    # places are what the card is for. Distances are computed and the list trimmed afterwards.
    return "[out:json][timeout:25];\n(\n" + "\n".join(clauses) + "\n);\nout center;"


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    radius = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return round(2 * radius * math.asin(math.sqrt(a)))


def _address_of(tags: dict) -> str | None:
    street, number = tags.get("addr:street"), tags.get("addr:housenumber")
    if not street:
        return None
    return f"{street} {number}".strip() if number else street


def _classify(tags: dict) -> tuple[str, str] | None:
    for label, key, values in _GROUPS:
        value = tags.get(key)
        if value in values:
            return label, values[value]
    return None


class OverpassNearbyTool:
    """`transport` is exposed purely so tests can inject `httpx.MockTransport`."""

    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float | None = None) -> None:
        # `timeout` overrides every attempt's own (tests use it); normally each server has its own.
        self._timeout = timeout
        self._client = httpx.Client(transport=transport, headers={"User-Agent": _USER_AGENT})

    def nearby(self, latitude: float, longitude: float, radius_m: int = NEARBY_RADIUS_M) -> NearbyPlaces:
        cache_key = (round(latitude, 4), round(longitude, 4), radius_m)
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
        if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]

        try:
            result = self._nearby_uncached(latitude, longitude, radius_m)
        except ToolExecutionError:
            if cached and time.monotonic() - cached[0] < _STALE_OK_SECONDS:
                return cached[1]
            raise
        with _CACHE_LOCK:
            _CACHE[cache_key] = (time.monotonic(), result)
        return result

    def _fetch_elements(self, query: str) -> list[dict]:
        last_error: Exception | None = None
        attempts = [*_OVERPASS_ATTEMPTS, _OVERPASS_ATTEMPTS[0]]
        for attempt, (url, timeout) in enumerate(attempts):
            if attempt == len(_OVERPASS_ATTEMPTS):
                time.sleep(_RETRY_FIRST_AFTER_SECONDS)  # last resort: the first server again, once it has cooled
            try:
                response = self._client.post(url, data={"data": query}, timeout=self._timeout or timeout)
                response.raise_for_status()
                return response.json().get("elements", [])
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
        raise ToolExecutionError(f"Overpass query failed on every server: {last_error}") from last_error

    def _nearby_uncached(self, latitude: float, longitude: float, radius_m: int) -> NearbyPlaces:
        elements = self._fetch_elements(_query(latitude, longitude, radius_m))

        found: dict[str, list[NearbyItem]] = {}
        seen: set[tuple[str, str, int]] = set()
        for element in elements:
            tags = element.get("tags") or {}
            classified = _classify(tags)
            if classified is None:
                continue
            lat = element.get("lat", (element.get("center") or {}).get("lat"))
            lon = element.get("lon", (element.get("center") or {}).get("lon"))
            name = tags.get("name:en") or tags.get("name")
            if lat is None or lon is None or not name:
                continue
            label, kind = classified
            distance = _distance_m(latitude, longitude, lat, lon)
            # OSM often maps one stop/entrance as several nodes; collapse exact repeats.
            key = (label, name, distance // 25)
            if key in seen:
                continue
            seen.add(key)
            found.setdefault(label, []).append(
                NearbyItem(
                    name=name,
                    kind=kind,
                    distance_m=distance,
                    latitude=lat,
                    longitude=lon,
                    opening_hours=tags.get("opening_hours"),
                    website=tags.get("website") or tags.get("contact:website"),
                    phone=tags.get("phone") or tags.get("contact:phone"),
                    cuisine=(tags.get("cuisine") or "").replace(";", ", ").replace("_", " ") or None,
                    address=_address_of(tags),
                    wheelchair=tags.get("wheelchair"),
                )
            )

        groups = []
        for label, items in found.items():
            items.sort(key=lambda item: item.distance_m)
            groups.append(NearbyGroup(label=label, total=len(items), nearest=items[:_MAX_LISTED_PER_GROUP]))
        groups.sort(key=lambda group: group.nearest[0].distance_m)

        return NearbyPlaces(latitude=latitude, longitude=longitude, radius_m=radius_m, groups=groups)
