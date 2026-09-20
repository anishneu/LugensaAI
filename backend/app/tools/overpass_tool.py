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

# The main public server sheds load with 429/504 fairly often, and measured against 15 places it
# failed on 6 (each after a long wait) when hit back to back, yet answered in ~6 s a minute later.
# So: independent mirrors, a short per-attempt timeout, and one retry of the primary after a pause.
# Two other mirrors that were once popular (overpass.openstreetmap.fr, maps.mail.ru) now refuse
# or time out for this query and were dropped after testing.
_OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
_RETRY_PRIMARY_AFTER_SECONDS = 2.0
_CACHE_TTL_SECONDS = 10 * 60
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
_MAX_LISTED_PER_GROUP = 3


def _query(lat: float, lon: float, radius_m: int) -> str:
    clauses = []
    for _, key, values in _GROUPS:
        pattern = "|".join(values)
        clauses.append(f'  nwr(around:{radius_m},{lat},{lon})["{key}"~"^({pattern})$"];')
    return "[out:json][timeout:25];\n(\n" + "\n".join(clauses) + "\n);\nout center 400;"


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    radius = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return round(2 * radius * math.asin(math.sqrt(a)))


def _classify(tags: dict) -> tuple[str, str] | None:
    for label, key, values in _GROUPS:
        value = tags.get(key)
        if value in values:
            return label, values[value]
    return None


class OverpassNearbyTool:
    """`transport` is exposed purely so tests can inject `httpx.MockTransport`."""

    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = 15.0) -> None:
        self._client = httpx.Client(transport=transport, timeout=timeout, headers={"User-Agent": _USER_AGENT})

    def nearby(self, latitude: float, longitude: float, radius_m: int = 600) -> NearbyPlaces:
        cache_key = (round(latitude, 4), round(longitude, 4), radius_m)
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
                return cached[1]

        result = self._nearby_uncached(latitude, longitude, radius_m)
        with _CACHE_LOCK:
            _CACHE[cache_key] = (time.monotonic(), result)
        return result

    def _fetch_elements(self, query: str) -> list[dict]:
        last_error: Exception | None = None
        for attempt, url in enumerate((*_OVERPASS_URLS, _OVERPASS_URLS[0])):
            if attempt == len(_OVERPASS_URLS):
                time.sleep(_RETRY_PRIMARY_AFTER_SECONDS)  # last resort: the primary again, once it has cooled
            try:
                response = self._client.post(url, data={"data": query})
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
            found.setdefault(label, []).append(NearbyItem(name=name, kind=kind, distance_m=distance))

        groups = []
        for label, items in found.items():
            items.sort(key=lambda item: item.distance_m)
            groups.append(NearbyGroup(label=label, total=len(items), nearest=items[:_MAX_LISTED_PER_GROUP]))
        groups.sort(key=lambda group: group.nearest[0].distance_m)

        return NearbyPlaces(latitude=latitude, longitude=longitude, radius_m=radius_m, groups=groups)
