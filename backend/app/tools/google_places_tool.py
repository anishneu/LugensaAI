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

Live testing showed the `reviews` field can come back absent (for a busy place,
on both Text Search and Place Details) while `reviewSummary` — Google's own AI
summary of all the reviews, with a "Summarized with Gemini" disclosure — comes
back fine. So the summary is requested and kept too, and labeled as Google's
summary rather than passed off as a reviewer's words.

Reviews are requested in English (`languageCode: "en"`), so Google returns its
own translation of non-English reviews; the original text and language are kept
and the UI labels them.

Covered by tests with a mocked transport, and checked once against the live API
(one Tokyo cafe: rating, review count, price, hours and the review summary all
came back correctly).
"""

from __future__ import annotations

import math
import threading
import time
from datetime import datetime

import httpx

from app.models.place_profile import PlaceProfile, PlaceReview
from app.tools.base import ToolConfigurationError, ToolExecutionError
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


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
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
        price_level=_PRICE_LABELS.get(place.get("priceLevel", "")),
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
            distance = _distance_m(latitude, longitude, location["latitude"], location["longitude"])
            display_name = _text_of(place.get("displayName")) or ""
            if distance <= _MAX_MATCH_DISTANCE_M and _mentions_business(display_name, name):
                matches.append((distance, place))
        if not matches:
            return None
        return _profile(min(matches, key=lambda m: m[0])[1])
