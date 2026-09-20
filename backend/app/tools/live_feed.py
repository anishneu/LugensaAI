"""The live feed: what is new, in the last 30 days, at and around a place.

Where it looks, in order, stopping at the first that has anything:
  1. "near": the pin's own name and the street and neighbourhood it is on (from a reverse geocode), each searched by name;
  2. "city": the city, when nothing at all was found near the pin. There is nearly always something about a city in a month;
     when there is not even that, the feed is empty and shows nothing.
Every item says which of the two it is about (`feed_place`), so a reader sees "Massachusetts Avenue" or "Cambridge" on it.

What it looks for: news outlets' headlines (Google News RSS, free, dated), Reddit's last 30 days (the free archive), and,
only as a fallback when those give too little, the billed Tavily search. What it leaves out: politics and things that are
irrelevant to a place (`feed_topics.excluded`). Each item is categorised (crime, accidents, weather, business, events,
development, community, news) for the reader to filter.

Nothing here is invented: an item with no readable date is not shown, and an empty result is an empty list.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.models.evidence import Evidence, SourceType
from app.models.location import Location
from app.tools.community_sources import base_name, without_admin_prefix
from app.tools.feed_topics import categorize, excluded
from app.tools.news_rss import GoogleNewsRss, NewsItem
from app.tools.tavily_tools import (
    LIVE_FEED_WINDOW_DAYS,
    _is_non_activity_url,
    _is_relevant_to_live_feed,
    _within_window,
)
from app.tools.translation import Translator, translate_evidence

_MAX_LOCAL_NAMES = 3
_MIN_CITY_ITEMS = 3  # below this, and with a key, the billed search is tried as well
_MAX_ITEMS = 60
_CACHE_TTL_SECONDS = 30 * 60
_WORKERS = 4
_MAX_TRANSLATIONS = 10

# Safety, then business and tourism: one query for whatever the city is in the news for, one each for the two kinds a person
# weighing a place cares about most, so a busy city's crime does not push its restaurants and events out of the top results.
_CITY_FACETS = (
    "",
    "(police OR crime OR arrested OR fire OR crash OR accident OR shooting OR stabbing OR robbery)",
    "(opens OR opening OR closing OR restaurant OR festival OR event OR tourism OR tourists OR construction OR hotel OR market)",
)
_ADDRESS_STREET_KEYS = ("road", "pedestrian", "footway")
_ADDRESS_AREA_KEYS = ("neighbourhood", "suburb", "quarter", "city_district", "borough")

_FEED_CACHE: dict[tuple, tuple[float, list[Evidence]]] = {}
_FEED_LOCK = threading.Lock()
_INFLIGHT: dict[tuple, threading.Lock] = {}
_ADDRESS_CACHE: dict[tuple[float, float], dict] = {}


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _splits(name: str) -> list[str]:
    """"Hunts Bank & Victoria Station Approach" is two places (a corner): each is searched on its own."""
    return [part.strip() for part in re.split(r"\s+(?:&|and|at|near)\s+|\s*[/,;]\s*|\s+-\s+", name) if part.strip()]


def _is_near(item: NewsItem, name: str, city: str, region: str) -> bool:
    """Whether a headline is about `name` in this city, and not about another thing called that. A street's name is shared
    (a search for "Broadway" in Cambridge, Massachusetts, returned New York theatre news), and OpenStreetMap's own
    neighbourhood for a point can be the wrong one, so the headline must name the street or area and also the city or region,
    or come from an outlet named for the city or the area ("harvardsquare.com")."""
    title = item.title.lower()
    publisher = _compact(item.publisher)
    named = re.search(rf"(?<!\w){re.escape(name.lower())}(?!\w)", title) is not None
    # An outlet that is a website named for the area ("harvardsquare.com"). Not any outlet whose name contains it: a theatre
    # site called "Broadway News" is not the street.
    site = item.publisher.lower().split(".")[0] if "." in item.publisher else ""
    from_here = bool(_compact(name)) and _compact(name) == _compact(site)
    if not (named or from_here):
        return False
    placed = any(place and (place.lower() in title or _compact(place) in publisher) for place in (city, region))
    return placed or from_here


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())[:70]


def _cache_key(location: Location) -> tuple:
    return (
        round(location.latitude or 0.0, 4),
        round(location.longitude or 0.0, 4),
        (location.name or "").lower(),
        (location.city or "").lower(),
    )


class LiveFeedTool:
    """`geocoder` needs a `reverse(lat, lon, language, zoom)` (a `NominatimClient`); `tavily` is an optional
    `TavilyLiveFeedTool` used only as a fallback; `reddit_archive` an optional `RedditArchiveTool`."""

    def __init__(
        self,
        rss: GoogleNewsRss | None = None,
        geocoder: object | None = None,
        reddit_archive: object | None = None,
        tavily: object | None = None,
        translator: Translator | None = None,
    ) -> None:
        self._rss = rss
        self._geocoder = geocoder
        self._archive = reddit_archive
        self._tavily = tavily
        self._translator = translator

    # ------------------------------------------------------------------ entry point
    def fetch(self, location: Location, *, refresh: bool = False) -> list[Evidence]:
        key = _cache_key(location)
        with _FEED_LOCK:
            gate = _INFLIGHT.setdefault(key, threading.Lock())
        with gate:  # two loads of one place at once (React's dev mode) share one set of requests
            if not refresh:
                with _FEED_LOCK:
                    cached = _FEED_CACHE.get(key)
                if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
                    return [item.model_copy(deep=True) for item in cached[1]]
            feed = self._build(location, refresh)
            with _FEED_LOCK:
                _FEED_CACHE[key] = (time.monotonic(), feed)
            return [item.model_copy(deep=True) for item in feed]

    def _build(self, location: Location, refresh: bool) -> list[Evidence]:
        address = self._address(location)
        city = self._city(location, address)
        names = self._local_names(location, address, city)
        country_code = location.country_code or (address.get("country_code") or "").lower() or None
        posts = self._recent_posts(location)

        near = self._near_news(names, city, location, country_code)
        near += [self._community(post, "near", name) for post in posts if (name := _mentioned(post, names))]
        if near:
            return self._finish(near, location)

        # Nothing at or around the pin: the city.
        items = self._city_news(city, location, country_code) + [self._community(post, "city", city) for post in posts]
        if self._tavily is not None and len(self._finish(list(items), location, translate=False)) < _MIN_CITY_ITEMS:
            items += self._fallback(location, city, refresh)
        return self._finish(items, location)

    # ------------------------------------------------------------------ where
    def _address(self, location: Location) -> dict:
        """The address parts of the pin (street, neighbourhood...), in English. Empty when it cannot be looked up."""
        if self._geocoder is None or location.latitude is None or location.longitude is None:
            return {}
        key = (round(location.latitude, 4), round(location.longitude, 4))
        with _FEED_LOCK:
            if key in _ADDRESS_CACHE:
                return _ADDRESS_CACHE[key]
        try:
            found = self._geocoder.reverse(location.latitude, location.longitude, "en", zoom=18)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - a lookup that fails only means no street-level names
            return {}
        address = found.get("address") or {}
        with _FEED_LOCK:
            _ADDRESS_CACHE[key] = address
        return address

    @staticmethod
    def _city(location: Location, address: dict) -> str:
        for candidate in (location.city, address.get("city"), address.get("town"), address.get("village"), address.get("municipality"), location.region, location.country):
            if candidate:
                return without_admin_prefix(str(candidate))
        return base_name(location.name)

    @staticmethod
    def _local_names(location: Location, address: dict, city: str) -> list[str]:
        """What is smaller than the city and names where the pin is: its own name, its street, its neighbourhood. A pin that
        is the city itself has none: the street at a city's centre point says nothing about the city."""
        wide = {n.lower() for n in (city, location.city, location.region, location.country) if n}
        if base_name(location.name).lower() in wide:
            return []
        names: list[str] = []

        def add(raw: object) -> None:
            for part in _splits(base_name(str(raw or ""))):
                low = part.lower()
                if len(part) < 4 or low in wide or "unnamed" in low or any(low == n.lower() for n in names):
                    continue
                names.append(part)

        add(location.name)
        for keys in (_ADDRESS_STREET_KEYS, _ADDRESS_AREA_KEYS):
            for key in keys:
                add(address.get(key))
        return names[:_MAX_LOCAL_NAMES]

    @staticmethod
    def _region(city: str, location: Location) -> str:
        """The region to add to a search so a shared city name means this one (Cambridge, Massachusetts), or ""."""
        region = without_admin_prefix(location.region or "")
        return region if region and region.lower() != city.lower() else ""

    # ------------------------------------------------------------------ news
    def _search(self, queries: list[tuple[str, str]], country_code: str | None) -> list[tuple[str, NewsItem]]:
        """Runs (label, query) searches together; returns (label, item) for every headline found."""
        if self._rss is None or not queries:
            return []
        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            results = list(pool.map(lambda lq: (lq[0], self._rss.search(lq[1], LIVE_FEED_WINDOW_DAYS, country_code)), queries))  # type: ignore[union-attr]
        return [(label, item) for label, found in results for item in found]

    def _news(self, item: NewsItem, scope: str, place: str, location: Location) -> Evidence:
        return Evidence(
            evidence_id="rss:" + hashlib.sha1(item.url.encode()).hexdigest()[:14],
            source_url=item.url,
            source_title=item.title,
            publisher=item.publisher or None,
            source_type=SourceType.NEWS,
            retrieved_at=datetime.now(timezone.utc),
            published_at=item.published_at,
            location_scope=place,
            text="",
            topic="live_feed",
            metadata={
                "provider": "google_news_rss",
                "feed_kind": "news",
                "feed_scope": scope,
                "feed_place": place,
                "feed_category": categorize(item.title),
            },
        )

    def _near_news(self, names: list[str], city: str, location: Location, country_code: str | None) -> list[Evidence]:
        region = self._region(city, location)
        found = self._search([(name, f'"{name}" {city} {region}'.strip()) for name in names], country_code)
        return [self._news(item, "near", name, location) for name, item in found if _is_near(item, name, city, region)]

    def _city_news(self, city: str, location: Location, country_code: str | None) -> list[Evidence]:
        region = self._region(city, location)
        found = self._search([(city, " ".join(part for part in (f'"{city}"', region, facet) if part)) for facet in _CITY_FACETS], country_code)
        return [self._news(item, "city", city, location) for _label, item in found]

    # ------------------------------------------------------------------ Reddit and the fallback
    def _recent_posts(self, location: Location) -> list[Evidence]:
        if self._archive is None:
            return []
        try:
            posts = self._archive.recent(location, LIVE_FEED_WINDOW_DAYS)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - a free extra source must never stop the feed
            return []
        return [
            post
            for post in posts
            if not _is_non_activity_url(post.source_url)
            and _is_relevant_to_live_feed(post.source_title, post.text, location, f"{post.source_url} {post.publisher or ''}")
        ]

    @staticmethod
    def _community(post: Evidence, scope: str, place: str) -> Evidence:
        item = post.model_copy(deep=True)
        item.location_scope = place
        item.metadata.update(
            {
                "feed_kind": "community",
                "feed_scope": scope,
                "feed_place": place,
                "feed_category": categorize(item.source_title, item.text, community=True),
            }
        )
        return item

    def _fallback(self, location: Location, city: str, refresh: bool) -> list[Evidence]:
        """The billed search, for a place the free sources say little about. Its items are about the city."""
        try:
            found = self._tavily.fetch(location, refresh=refresh)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 - the feed is best effort; a billed search failing is not worth an error
            return []
        items = []
        for item in found:
            kind = "community" if item.metadata.get("feed_kind") == "community" else "news"
            item.location_scope = city
            item.metadata.update(
                {
                    "feed_kind": kind,
                    "feed_scope": "city",
                    "feed_place": city,
                    "feed_category": categorize(item.source_title, item.text, community=kind == "community"),
                }
            )
            items.append(item)
        return items

    # ------------------------------------------------------------------ what is kept
    def _finish(self, items: list[Evidence], location: Location, *, translate: bool = True) -> list[Evidence]:
        """Political and irrelevant items out, only the last 30 days, no repeats, newest first."""
        kept = [item for item in items if excluded(item.source_title, item.text, community=item.metadata.get("feed_kind") == "community") is None]
        kept = _within_window(kept)
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        unique: list[Evidence] = []
        for item in sorted(kept, key=lambda e: e.published_at, reverse=True):  # type: ignore[arg-type,return-value]
            title = _norm_title(item.source_title)
            if item.source_url in seen_urls or title in seen_titles:
                continue  # the same story from the same outlet twice, or syndicated under one headline
            seen_urls.add(item.source_url)
            seen_titles.add(title)
            unique.append(item)
        unique = unique[:_MAX_ITEMS]
        if translate and self._translator is not None:
            translate_evidence([i for i in unique if i.metadata.get("feed_kind") == "community"], self._translator, max_translations=_MAX_TRANSLATIONS)
        return unique


def _mentioned(post: Evidence, names: list[str]) -> str | None:
    """The street, neighbourhood or place name a post's headline or opening text mentions, if any."""
    haystack = f"{post.source_title} {post.text}".lower()
    return next((name for name in names if re.search(rf"(?<!\w){re.escape(name.lower())}(?!\w)", haystack)), None)
