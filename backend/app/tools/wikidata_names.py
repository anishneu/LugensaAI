"""Other English names for a place, from Wikidata (free, no key).

Romanised names are spelled differently from page to page: the Thai dam Google calls "Pa Sak Jolasid Dam" is "Pasak
Chonlasit Dam" on Wikipedia and "Pa Sak Cholasit" on TripAdvisor. A page about it that uses another spelling has none of the
words the search and the place filters look for, and is lost. Wikidata keeps a label and aliases for a place, so this looks
the place up there and returns them, for matching (`Location.name_variants`) and for searching the Reddit archive.

Only an entity whose coordinates are near the pin counts, so a same-named place elsewhere cannot lend its names. Best
effort: any failure, or a place with no Wikidata entry (most small businesses), returns no variants and changes nothing.
"""

from __future__ import annotations

import threading

import httpx

from app.tools.google_places_tool import distance_m
from app.tools.wiki_tool import _USER_AGENT

_API = "https://www.wikidata.org/w/api.php"
# Wide, because a Wikidata point for a dam or a park is its centre, and the pin may be a station or a viewpoint on it.
_MAX_DISTANCE_M = 20_000
_MAX_CANDIDATES = 5
_MAX_VARIANTS = 6
_CACHE: dict[tuple[str, float, float], list[str]] = {}
_CACHE_LOCK = threading.Lock()


def _search_strings(name: str) -> list[str]:
    """What to look up: the name, and what follows an " at " in it ("Floating Train at Pa Sak Jolasid Dam" is a listing
    of a train on a place that has an entry of its own, "Pa Sak Jolasid Dam")."""
    strings = [name.strip()]
    if " at " in name:
        tail = name.split(" at ", 1)[1].strip()
        if len(tail) >= 4:
            strings.append(tail)
    return strings


class WikidataNameVariants:
    """`transport` is exposed purely so tests can inject `httpx.MockTransport`."""

    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = 8.0) -> None:
        self._client = httpx.Client(transport=transport, timeout=timeout, headers={"User-Agent": _USER_AGENT})

    def variants(self, name: str, latitude: float | None, longitude: float | None) -> list[str]:
        """The other English names of the place called `name` at these coordinates; empty when unknown or unsure."""
        if not name.strip() or latitude is None or longitude is None:
            return []
        key = (name.lower(), round(latitude, 2), round(longitude, 2))
        with _CACHE_LOCK:
            if key in _CACHE:
                return list(_CACHE[key])
        try:
            found = self._lookup(name, latitude, longitude)
        except (httpx.HTTPError, ValueError, KeyError):
            return []  # not cached: the next request may work
        with _CACHE_LOCK:
            _CACHE[key] = found
        return list(found)

    def _lookup(self, name: str, latitude: float, longitude: float) -> list[str]:
        ids: list[str] = []
        for text in _search_strings(name):
            search = self._client.get(
                _API,
                params={"action": "wbsearchentities", "search": text, "language": "en", "uselang": "en", "type": "item", "limit": _MAX_CANDIDATES, "format": "json"},
            )
            search.raise_for_status()
            ids += [item["id"] for item in search.json().get("search", []) if item["id"] not in ids]
        ids = ids[: _MAX_CANDIDATES * 2]
        if not ids:
            return []
        entities = self._client.get(
            _API,
            params={"action": "wbgetentities", "ids": "|".join(ids), "props": "labels|aliases|claims", "languages": "en", "format": "json"},
        )
        entities.raise_for_status()

        names: list[str] = []
        for entity in entities.json().get("entities", {}).values():
            if not self._is_here(entity, latitude, longitude):
                continue
            candidates = [entity.get("labels", {}).get("en", {}).get("value", "")]
            candidates += [alias.get("value", "") for alias in entity.get("aliases", {}).get("en", [])]
            for candidate in candidates:
                # The entity was found by the place's name and sits at its coordinates; all its English names are the place's.
                if candidate and candidate.lower() != name.lower() and candidate not in names:
                    names.append(candidate)
        return names[:_MAX_VARIANTS]

    @staticmethod
    def _is_here(entity: dict, latitude: float, longitude: float) -> bool:
        for claim in entity.get("claims", {}).get("P625", []):
            value = (claim.get("mainsnak", {}).get("datavalue") or {}).get("value") or {}
            if "latitude" in value and "longitude" in value:
                if distance_m(latitude, longitude, value["latitude"], value["longitude"]) <= _MAX_DISTANCE_M:
                    return True
        return False
