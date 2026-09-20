"""Ratings, reviews and hours for one specific business, from Google Places.

Why this exists: for a single cafe or hotel, open-web search finds a couple of
pages while Google Maps has hundreds of dated reviews. That gap can't be closed
by prompting a model harder. Google's Places API (New) is the legitimate way
to get that data; scraping Maps breaks its terms.

Optional and off by default. It needs `GOOGLE_PLACES_API_KEY` from a Google
Cloud project **with billing enabled** (a card on file). Google gives a monthly
free allowance per product, but the reviews fields are in the more expensive
"Enterprise + Atmosphere" tier — check current pricing before enabling. One
lookup is made per place and cached in memory for 30 minutes, so asking several
questions about the same place doesn't bill several times.

Matching is deliberately strict: the result must be within a few hundred meters
of the pin AND carry the business's distinguishing name words, otherwise
`lookup()` returns None. Showing another business's 4.8 stars is worse than
showing none.

Google's own AI summary of all the reviews (`reviewSummary`, with a "Summarized
with Gemini" disclosure) is requested and kept too, and labeled as Google's
summary rather than passed off as a reviewer's words. Note that the auto-created
"Maps Platform demo" API key returns the rating, count and summary but never
`reviews` or `photos` (not even for the Eiffel Tower); a key from your own project
with billing enabled returns up to five real, dated reviews and ten photos.

Reviews are requested in English (`languageCode: "en"`), so Google returns its
own translation of non-English reviews; the original text and language are kept
and the UI labels them.

Covered by tests with a mocked transport, and checked against the live API (a
restaurant in Kurume and a cafe in a German village: rating, review count, price
range, hours, the review summary and five dated reviews all matched Google Maps).
"""

from __future__ import annotations

import math
import re
import threading
import time
import unicodedata
from datetime import datetime

import httpx

from app.models.location import Location
from app.models.place import PlaceCandidate
from app.models.place_profile import PlaceProfile, PlaceReview
from app.tools.base import LocationNotFoundError, LocationResolverTool, ToolConfigurationError, ToolExecutionError
from app.tools.nominatim_tool import slugify
from app.tools.tavily_tools import _mentions_business

_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.priceLevel",
        "places.priceRange",
        "places.googleMapsUri",
        "places.websiteUri",
        "places.nationalPhoneNumber",
        "places.regularOpeningHours.weekdayDescriptions",
        "places.currentOpeningHours.openNow",
        "places.editorialSummary",
        "places.reviewSummary",
        "places.reviews",
    ]
)
_MAX_MATCH_DISTANCE_M = 400
_CACHE_TTL_SECONDS = 30 * 60
_CACHE: dict[tuple[str, float, float], tuple[float, PlaceProfile | None]] = {}
_CACHE_LOCK = threading.Lock()

_PRICE_LABELS = {
    "PRICE_LEVEL_FREE": "Free",
    "PRICE_LEVEL_INEXPENSIVE": "$",
    "PRICE_LEVEL_MODERATE": "$$",
    "PRICE_LEVEL_EXPENSIVE": "$$$",
    "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$",
}
_CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "JPY": "¥", "CNY": "¥", "KRW": "₩", "INR": "₹", "BRL": "R$", "TRY": "₺"}


def _price_text(place: dict) -> str | None:
    """What Google Maps prints next to the rating ("€10–20").

    Its `priceRange` is a real per-person range in the local currency. The generic $/$$/$$$ level is
    only a fallback: outside the dollar zone it reads as a currency that isn't used there.
    """
    price_range = place.get("priceRange") if isinstance(place.get("priceRange"), dict) else {}
    start, end = price_range.get("startPrice") or {}, price_range.get("endPrice") or {}
    currency = start.get("currencyCode") or end.get("currencyCode")
    low, high = start.get("units"), end.get("units")
    if currency and (low or high):
        symbol = _CURRENCY_SYMBOLS.get(currency, f"{currency} ")
        if low and high:
            return f"{symbol}{low}–{high}"
        return f"{symbol}{low}+" if low else f"up to {symbol}{high}"
    return _PRICE_LABELS.get(place.get("priceLevel", ""))


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((phi2 - phi1) / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _text_of(node: object) -> str | None:
    return node.get("text") if isinstance(node, dict) and isinstance(node.get("text"), str) else None


def _review(raw: dict) -> PlaceReview | None:
    text = _text_of(raw.get("text")) or _text_of(raw.get("originalText"))
    if not text or not text.strip():
        return None
    original = raw.get("originalText") if isinstance(raw.get("originalText"), dict) else {}
    original_language = original.get("languageCode")
    original_text = _text_of(original)
    was_translated = bool(original_language and original_language != "en" and original_text and original_text != text)
    return PlaceReview(
        author=(raw.get("authorAttribution") or {}).get("displayName"),
        rating=raw.get("rating") if isinstance(raw.get("rating"), int) else None,
        text=text.strip(),
        original_text=original_text if was_translated else None,
        original_language=original_language if was_translated else None,
        published_at=_parse_time(raw.get("publishTime")),
        relative_time=raw.get("relativePublishTimeDescription"),
    )


def _profile(place: dict) -> PlaceProfile:
    hours = ((place.get("regularOpeningHours") or {}).get("weekdayDescriptions")) or []
    reviews = [r for r in (_review(raw) for raw in place.get("reviews") or []) if r is not None]
    review_summary = place.get("reviewSummary") if isinstance(place.get("reviewSummary"), dict) else {}
    return PlaceProfile(
        place_id=place["id"],
        name=_text_of(place.get("displayName")) or "",
        address=place.get("formattedAddress"),
        rating=place.get("rating"),
        review_count=place.get("userRatingCount"),
        price_level=_price_text(place),
        summary=_text_of(place.get("editorialSummary")),
        review_summary=_text_of(review_summary.get("text")),
        review_summary_disclosure=_text_of(review_summary.get("disclosureText")),
        review_summary_report_url=review_summary.get("flagContentUri"),
        open_now=(place.get("currentOpeningHours") or {}).get("openNow"),
        opening_hours=list(hours),
        website=place.get("websiteUri"),
        phone=place.get("nationalPhoneNumber"),
        maps_url=place.get("googleMapsUri"),
        reviews=reviews,
    )


# Only what is needed to place a pin and label it. Deliberately without ratings
# or reviews: those are the pricier fields and are fetched once, by `lookup()`,
# after the user commits to a place, not on every search.
_SEARCH_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.addressComponents",
        "places.location",
        "places.types",
        "places.primaryTypeDisplayName",
    ]
)
_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
_SEARCH_CACHE_TTL_SECONDS = 10 * 60
_SEARCH_CACHE: dict[tuple[str, int], tuple[float, list[PlaceCandidate]]] = {}
# A pasted Google plus code: "8JG8+44", optionally with a locality ("8JG8+44 Kurume").
_PLUS_CODE_RE = re.compile(r"^[23456789CFGHJMPQRVWX]{2,8}\+[23456789CFGHJMPQRVWX]{2,3}(\s|,|$)", re.IGNORECASE)
# Google puts `establishment` on *anything with a listing*, including islands, beaches, parks and
# monuments ("Victoria Island" in Lagos, "Bondi Beach"). Those are places, not a business a person
# reviews, and researching them as one (strict name matching, "customer reviews" queries) finds nothing.
_VENUE_MARKERS = frozenset({"establishment", "point_of_interest"})
_NOT_A_VENUE_TYPES = frozenset(
    {
        "natural_feature", "island", "beach", "park", "national_park", "garden", "historical_landmark",
        "monument", "cemetery", "place_of_worship", "bridge", "campground", "hiking_area", "plaza",
    }
)


# Google's own labels for "a street address / a building / a bare point", as opposed to a named place.
_ADDRESS_MARKERS = frozenset({"street_address", "premise", "subpremise", "plus_code"})


def is_address_only(types: set[str]) -> bool:
    return bool(types & _ADDRESS_MARKERS) and not is_venue(types)


def is_venue(types: set[str]) -> bool:
    return bool(types & _VENUE_MARKERS) and not (types & _NOT_A_VENUE_TYPES)


def _fold(text: str) -> str:
    """Lower-case with accents removed, so "Sao Paulo" matches "São Paulo"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _prefer_locality(candidates: list[PlaceCandidate], query: str) -> list[PlaceCandidate]:
    """Put results that mention the locality the user typed first.

    "Sukhumvit, Bangkok" returned "Sukhumvit Road", a 400 km road whose point sat 158 km from Bangkok.
    The text after the last comma is the user's own statement of where they mean, so results whose
    address contains it are ranked ahead of those that don't. Nothing is dropped, only reordered.
    """
    segments = [s.strip() for s in query.split(",") if s.strip()]
    if len(segments) < 2:
        return candidates
    hint = _fold(segments[-1])
    if len(hint) < 3:
        return candidates
    return sorted(candidates, key=lambda c: hint not in _fold(c.display_name))
_NEARBY_RADIUS_M = 40.0
_LOCALITY_BIAS_RADIUS_M = 20_000.0


def looks_like_plus_code(query: str) -> bool:
    return bool(_PLUS_CODE_RE.match(query.strip()))


def _component(place: dict, *wanted: str) -> str | None:
    for component in place.get("addressComponents") or []:
        if any(kind in (component.get("types") or []) for kind in wanted):
            return component.get("longText")
    return None


def _display_name(name: str, address: str | None) -> str:
    """"Cafe X, 1 Main St, Town". A street address is its own name ("Unterer Graben 11"), and Google's
    formatted address already starts with it, so repeating it read "Unterer Graben 11, Unterer Graben 11, ..."."""
    if not address:
        return name
    return address if address.lower().startswith(name.lower()) else f"{name}, {address}"


def _candidate(place: dict) -> PlaceCandidate | None:
    location = place.get("location") or {}
    name = _text_of(place.get("displayName"))
    if not name or "latitude" not in location or "longitude" not in location:
        return None
    types = set(place.get("types") or [])
    return PlaceCandidate(
        name=name,
        display_name=_display_name(name, place.get("formattedAddress")),
        category=_text_of(place.get("primaryTypeDisplayName")) or (place.get("types") or ["place"])[0],
        city=_component(place, "locality", "postal_town", "administrative_area_level_2"),
        region=_component(place, "administrative_area_level_1"),
        country=_component(place, "country"),
        latitude=location["latitude"],
        longitude=location["longitude"],
        is_business=is_venue(types),
        is_address=is_address_only(types),
    )


class GooglePlacesTool:
    """`transport` is exposed purely so tests can inject `httpx.MockTransport`."""

    def __init__(
        self, api_key: str | None = None, transport: httpx.BaseTransport | None = None, timeout: float = 20.0
    ) -> None:
        if not api_key:
            raise ToolConfigurationError("GooglePlacesTool requires an api_key (GOOGLE_PLACES_API_KEY).")
        self._client = httpx.Client(
            transport=transport,
            timeout=timeout,
            headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": _FIELD_MASK, "Content-Type": "application/json"},
        )

    def _post(self, url: str, body: dict, field_mask: str) -> list[dict]:
        try:
            response = self._client.post(url, json=body, headers={"X-Goog-FieldMask": field_mask})
            response.raise_for_status()
            return response.json().get("places", [])
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolExecutionError(f"Google Places request failed: {exc}") from exc

    def _retry_near_locality(self, query: str, candidates: list[PlaceCandidate], limit: int) -> list[PlaceCandidate]:
        """When nothing Google returned is in the locality the user typed, search again around it.

        "Sukhumvit, Bangkok" got a 400 km road whose point was 158 km from Bangkok, and no other
        candidate. Biasing the same search to a circle around Bangkok returns roads inside it.
        Costs two extra calls, and only in this mismatch case.
        """
        segments = [s.strip() for s in query.split(",") if s.strip()]
        if len(segments) < 2 or not candidates:
            return candidates
        hint = segments[-1]
        if _fold(hint) in _fold(candidates[0].display_name):
            return candidates
        centre = self._post(_SEARCH_URL, {"textQuery": hint, "maxResultCount": 1, "languageCode": "en"}, _SEARCH_FIELD_MASK)
        if not centre or "latitude" not in (centre[0].get("location") or {}):
            return candidates
        biased = self._post(
            _SEARCH_URL,
            {
                "textQuery": ", ".join(segments[:-1]),
                "maxResultCount": limit,
                "languageCode": "en",
                "locationBias": {"circle": {"center": centre[0]["location"], "radius": _LOCALITY_BIAS_RADIUS_M}},
            },
            _SEARCH_FIELD_MASK,
        )
        nearby = [c for c in (_candidate(p) for p in biased) if c is not None]
        known = {(c.name, round(c.latitude, 3), round(c.longitude, 3)) for c in nearby}
        return nearby + [c for c in candidates if (c.name, round(c.latitude, 3), round(c.longitude, 3)) not in known]

    def venues_at(self, latitude: float, longitude: float, radius_m: float = _NEARBY_RADIUS_M) -> list[PlaceCandidate]:
        """The businesses standing at a point, nearest first.

        A street address or a pasted plus code names a spot, not a business, yet a cafe or shop is
        usually what the person means ("how is the cafe at this location?"). Google's nearby search
        finds it; OpenStreetMap doesn't list most small businesses.
        """
        nearby = self._post(
            _NEARBY_URL,
            {
                "maxResultCount": 5,
                "rankPreference": "DISTANCE",
                "languageCode": "en",
                "locationRestriction": {
                    "circle": {"center": {"latitude": latitude, "longitude": longitude}, "radius": radius_m}
                },
            },
            _SEARCH_FIELD_MASK,
        )
        return [c for c in (_candidate(p) for p in nearby) if c is not None and c.is_business]

    def search_places(self, query: str, limit: int = 5) -> list[PlaceCandidate]:
        """Find places by name, address or plus code the way Google Maps does.

        OpenStreetMap has no listing for most small businesses and doesn't
        understand plus codes ("8JG8+44 Kurume"), which is what Google Maps
        hands you when you share a spot. Google's own search resolves both.

        A plus code names a point, not a business, so the business standing on
        it is looked up too and listed first.
        """
        query = query.strip()
        if not query:
            return []
        cache_key = (query.lower(), limit)
        with _CACHE_LOCK:
            cached = _SEARCH_CACHE.get(cache_key)
            if cached and time.monotonic() - cached[0] < _SEARCH_CACHE_TTL_SECONDS:
                return cached[1]

        places = self._post(
            _SEARCH_URL, {"textQuery": query, "maxResultCount": limit, "languageCode": "en"}, _SEARCH_FIELD_MASK
        )
        candidates = _prefer_locality([c for c in (_candidate(p) for p in places) if c is not None], query)
        candidates = self._retry_near_locality(query, candidates, limit)

        if looks_like_plus_code(query) and candidates:
            anchor = candidates[0]
            candidates = self.venues_at(anchor.latitude, anchor.longitude)[:1] + candidates

        with _CACHE_LOCK:
            _SEARCH_CACHE[cache_key] = (time.monotonic(), candidates)
        return candidates

    def local_name(self, name: str, latitude: float, longitude: float, language: str) -> str | None:
        """A business's own name in `language` ("Suiran" -> "翠藍"): what local review sites call it.

        Same search, same place, asked for in the local language. Only a result within 150 m of the pin
        counts, so a same-named business elsewhere can't lend its name.
        """
        places = self._post(
            _SEARCH_URL,
            {
                "textQuery": name,
                "maxResultCount": 3,
                "languageCode": language,
                "locationBias": {"circle": {"center": {"latitude": latitude, "longitude": longitude}, "radius": 300.0}},
            },
            "places.displayName,places.location",
        )
        best: tuple[float, str] | None = None
        for place in places:
            spot = place.get("location") or {}
            label = _text_of(place.get("displayName"))
            if not label or "latitude" not in spot or "longitude" not in spot:
                continue
            distance = distance_m(latitude, longitude, spot["latitude"], spot["longitude"])
            if distance <= 150 and (best is None or distance < best[0]):
                best = (distance, label)
        return best[1] if best else None

    def lookup(self, name: str, latitude: float, longitude: float, area: str = "") -> PlaceProfile | None:
        cache_key = (name.lower(), round(latitude, 4), round(longitude, 4))
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
                return cached[1]

        profile = self._lookup_uncached(name, latitude, longitude, area)
        with _CACHE_LOCK:
            _CACHE[cache_key] = (time.monotonic(), profile)
        return profile

    def _lookup_uncached(self, name: str, latitude: float, longitude: float, area: str) -> PlaceProfile | None:
        body = {
            "textQuery": f"{name} {area}".strip(),
            "maxResultCount": 5,
            "languageCode": "en",
            "locationBias": {"circle": {"center": {"latitude": latitude, "longitude": longitude}, "radius": 500.0}},
        }
        try:
            response = self._client.post(_SEARCH_URL, json=body)
            response.raise_for_status()
            places = response.json().get("places", [])
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolExecutionError(f"Google Places lookup failed: {exc}") from exc

        matches = []
        for place in places:
            location = place.get("location") or {}
            if "latitude" not in location or "longitude" not in location or "id" not in place:
                continue
            distance = distance_m(latitude, longitude, location["latitude"], location["longitude"])
            display_name = _text_of(place.get("displayName")) or ""
            if distance <= _MAX_MATCH_DISTANCE_M and _mentions_business(display_name, name):
                matches.append((distance, place))
        if not matches:
            return None
        return _profile(min(matches, key=lambda m: m[0])[1])


class GooglePlacesLocationResolver(LocationResolverTool):
    """Resolves a free-text place through Google, for use ahead of OpenStreetMap.

    A Google failure is treated as "not found" so the chain moves on to the
    next resolver instead of failing the whole question.
    """

    def __init__(self, tool: GooglePlacesTool) -> None:
        self._tool = tool

    def resolve(self, raw_query: str) -> Location:
        try:
            candidates = self._tool.search_places(raw_query, limit=1)
        except ToolExecutionError as exc:
            raise LocationNotFoundError(f"Google could not resolve {raw_query!r}: {exc}") from exc
        if not candidates:
            raise LocationNotFoundError(f"Could not resolve location: {raw_query!r}")
        top = candidates[0]
        return Location(
            name=top.name,
            city=top.city,
            region=top.region,
            country=top.country,
            slug=slugify(f"{top.name}-{top.city or ''}-{top.latitude:.5f}-{top.longitude:.5f}"),
            latitude=top.latitude,
            longitude=top.longitude,
            raw_query=raw_query,
            is_business=top.is_business,
        )
