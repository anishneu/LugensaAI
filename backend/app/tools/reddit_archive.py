"""Reddit posts about a place, from Arctic Shift's free public archive of Reddit.

A web search returns a small, ranked sample of the internet, and Reddit is a poor fit for it: for a floating train in
Thailand a thread titled with the place's exact name existed and the search returned YouTube and Facebook pages instead. The
archive is Reddit itself, searchable by words in a post's title, so it can be asked directly: "posts in r/ThailandTourism
whose title has 'Jolasid'". It costs no search credit, and each post comes with its real posting time (no date recovery).

What it can and cannot do, measured:
* Text search needs a subreddit to look in (the archive refuses it otherwise), so the place's subreddits are found first
  by name prefix (r/erfurt, r/germany, r/ThailandTourism), plus a few big travel subreddits.
* It searches post titles. Comment search times out on the archive, so a place mentioned only in a comment is not found.
* Each title search takes several seconds and the archive rations them: past its budget it answers HTTP 429 with the seconds
  until the window resets (`x-ratelimit-reset`). Two back-to-back runs of twelve searches each were enough to be refused. So
  requests are few, run two at a time under one deadline, a refusal is waited out when it is short and otherwise stops the
  rest (never hammered), and every answer is cached for an hour, so a second question about the same place costs nothing.
  It is a third-party service: an outage just means no Reddit posts from here.

Everything it returns goes through the same place filters as a web result (`filter_for_place`).
"""

from __future__ import annotations

import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import httpx

from app.models.evidence import Evidence, SourceType
from app.models.location import Location
from app.models.plan import ResearchTopic
from app.tools.base import WebSearchTool
from app.tools.community_sources import place_names, search_area, without_admin_prefix
from app.tools.descriptions import readable_description
from app.tools.tavily_tools import _GENERIC_NAME_WORDS, _name_words, filter_for_place
from app.tools.translation import Translator, translate_evidence

_BASE = "https://arctic-shift.photon-reddit.com/api"
_USER_AGENT = "LugensaAI/1.0 (location research demo)"
_TRAVEL_SUBREDDITS = ("travel", "solotravel", "backpacking")
_MAX_SUBREDDITS = 8
_MAX_REQUESTS = 8
_POSTS_PER_REQUEST = 15
_MIN_SUBSCRIBERS = 200
# A community with a place qualifier in its name ('CambridgeMA') counts as another place only if it is a real one: an adult
# subreddit named 'Erfurtsex' with 300 members does not make Erfurt ambiguous.
_MIN_QUALIFIED_SUBSCRIBERS = 2000
_WORKERS = 2
_DEADLINE_SECONDS = 40.0
_MAX_TEXT_CHARS = 700
_RECENT_MAX = 30
_MAX_TRANSLATIONS = 8
_RETRY_AFTER_SECONDS = 1.5
# Longest a refusal is waited out; a longer one (the archive said 30 s) ends the search instead of holding a research run.
_MAX_WAIT_SECONDS = 12.0
_POSTS_CACHE_TTL_SECONDS = 60 * 60
_POSTS_CACHE: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_BLOCKED_UNTIL = 0.0
_SUBREDDIT_CACHE_TTL_SECONDS = 24 * 60 * 60
_SUBREDDIT_CACHE: dict[str, tuple[float, list[str]]] = {}
_CACHE_LOCK = threading.Lock()

# Words a place's name has that many other posts have too: a poor thing to search a title for.
_COMMON_PLACE_WORDS = frozenset(
    """floating train river mountain mountains national park temple market station museum palace castle beach bridge lake
    island garden gardens street square city old new great grand royal central north south east west dam tower church
    cathedral restaurant hotel hostel resort waterfall falls valley village town center centre plaza gate wall road highway
    airport university college school hospital""".split()
)
_REMOVED = {"[removed]", "[deleted]", ""}

# What a subreddit's own description may call a country, when the place's country is written another way ("United States" for
# a subreddit that says "USA"). Anything not listed is matched by its name alone.
_COUNTRY_ALIASES: dict[str, frozenset[str]] = {
    **{k: frozenset({"usa", "u.s.", "u.s.a.", "america", "united states", "united states of america"}) for k in ("united states", "united states of america", "usa", "us")},
    **{k: frozenset({"uk", "u.k.", "united kingdom", "great britain", "britain", "england", "scotland", "wales", "northern ireland"}) for k in ("united kingdom", "uk", "great britain", "england", "scotland", "wales")},
}
# Endings of a subreddit's name that name the same place in another way; anything else after the place's name and that is a
# place code (2 or 3 letters: "MA", "UK", "ont") names *which* place it is. (A 4-letter ending is not one: "KyotoSwap" is a
# crypto exchange, not another Kyoto.)
_SAME_PLACE_SUFFIXES = frozenset({"tourism", "travel", "travels", "traveling", "travelling", "city"})


def search_terms(names: list[str], area: frozenset[str] = frozenset()) -> list[str]:
    """What to look for in titles, per name: its longest word that is not a common one ("Jolasid" for "Floating Train at
    Pa Sak Jolasid Dam"), since the archive matches all the words it is given, and a post rarely repeats a whole name.
    When that word is only the name of the area ("Erfurt", for "Hotel Erfurt-City"), every post in the city's subreddit has
    it and the newest few would crowd out the one wanted, so it is searched with the next longest word ("erfurt city")."""
    terms: list[str] = []
    for name in names:
        words = [w for w in _name_words(name) if len(w) >= 4 and w not in _GENERIC_NAME_WORDS]
        rare = [w for w in words if w not in _COMMON_PLACE_WORDS] or words
        if not rare:
            continue
        term = max(rare, key=len)
        if term in area and len(words) >= 2:
            term = " ".join(sorted(words, key=len, reverse=True)[:2])
        if term not in terms:
            terms.append(term)
    return terms[:3]


def _slug(text: str) -> str:
    """"Thüringen" -> "thuringen": what a subreddit's name is made of."""
    folded = unicodedata.normalize("NFKD", without_admin_prefix(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", folded.lower())


class RedditArchiveTool(WebSearchTool):
    """`transport` is exposed purely so tests can inject `httpx.MockTransport`."""

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        translator: Translator | None = None,
        timeout: float = 25.0,
        deadline_seconds: float = _DEADLINE_SECONDS,
    ) -> None:
        self._client = httpx.Client(transport=transport, timeout=timeout, headers={"User-Agent": _USER_AGENT})
        self._translator = translator
        self._deadline = deadline_seconds

    # ------------------------------------------------------------------ which subreddits
    def _rows(self, prefix: str) -> list[dict] | None:
        """The archive's subreddits whose name starts with `prefix`, with their descriptions (cached a day)."""
        now = time.monotonic()
        with _CACHE_LOCK:
            cached = _SUBREDDIT_CACHE.get(prefix)
        if cached and now - cached[0] < _SUBREDDIT_CACHE_TTL_SECONDS:
            return cached[1]  # type: ignore[return-value]
        payload = self._get("/subreddits/search", {"subreddit_prefix": prefix, "limit": 20})
        if payload is None:
            return None  # refused or down: not cached, so the next question tries again
        rows = payload.get("data") or []
        with _CACHE_LOCK:
            _SUBREDDIT_CACHE[prefix] = (now, rows)  # type: ignore[assignment]
        return rows

    @staticmethod
    def _describes(row: dict, location: Location, long_text: bool = False) -> bool:
        """Whether the subreddit says it is about the place's region or country. By its title and short description; with
        `long_text` also by the start of its sidebar, which is looser (r/CambridgeMA's mentions England)."""
        text = " ".join(str(row.get(k) or "") for k in ("title", "public_description"))
        if long_text:
            text += " " + str(row.get("description") or "")[:400]
        text = text.lower()
        names = {n for n in (location.region, location.country) if n}
        forms: set[str] = set()
        for name in names:
            plain = without_admin_prefix(name).lower()
            forms.add(plain)
            forms |= _COUNTRY_ALIASES.get(name.lower(), frozenset())
        return any(re.search(rf"(?<![a-z]){re.escape(form)}(?![a-z])", text) for form in forms if form)

    def _discover(self, prefix: str, location: Location, verify: bool = False) -> list[str]:
        """The subreddits named for a place: r/erfurt, r/Thailand and r/ThailandTourism, but not r/ThailandBarGirls.

        With `verify` (a city's subreddit) the place must be the right one. City names are shared: r/cambridge is Cambridge,
        England, and a feed for Cambridge, Massachusetts, was filled with posts about the University of Cambridge. Where the
        name is shared (another subreddit carries a place qualifier: r/CambridgeMA, r/cambridgeont) a subreddit is used
        only if its own description names the place's region or country, and one with a qualifier of its own always must."""
        rows = self._rows(prefix)
        if rows is None:
            return []
        variants = re.compile(rf"{re.escape(prefix)}({'|'.join(_SAME_PLACE_SUFFIXES)})?", re.IGNORECASE)
        qualified = re.compile(rf"{re.escape(prefix)}[a-z]{{2,3}}", re.IGNORECASE)
        big = [r for r in rows if (r.get("subscribers") or 0) >= _MIN_SUBSCRIBERS]
        shared = any(
            qualified.fullmatch(str(r.get("display_name") or r.get("name") or ""))
            and str(r.get("display_name") or r.get("name") or "").lower()[len(prefix) :] not in _SAME_PLACE_SUFFIXES
            and (r.get("subscribers") or 0) >= _MIN_QUALIFIED_SUBSCRIBERS
            for r in big
        )

        # Of the subreddits that describe this place, prefer those whose own short description does; the sidebar only if none.
        short = any(self._describes(r, location) for r in big)
        found: list[str] = []
        for row in sorted(big, key=lambda r: -(r.get("subscribers") or 0)):
            name = str(row.get("display_name") or row.get("name") or "")
            is_variant = bool(variants.fullmatch(name))
            is_qualified = bool(qualified.fullmatch(name)) and not is_variant and (row.get("subscribers") or 0) >= _MIN_QUALIFIED_SUBSCRIBERS
            if not (is_variant or (verify and is_qualified)):
                continue
            if verify and (is_qualified or shared) and not self._describes(row, location, long_text=not short):
                continue
            found.append(name)
        return found[:2]

    def geo_subreddits(self, location: Location) -> list[tuple[str, str]]:
        """The subreddits named for the place, each with the level it is named for: "city", "region" or "country"."""
        chosen: list[tuple[str, str]] = []
        seen_prefixes: set[str] = set()
        for level, text in (("city", location.city), ("region", location.region), ("country", location.country)):
            prefix = _slug(text) if text else ""
            if len(prefix) < 4 or prefix in seen_prefixes:
                continue
            seen_prefixes.add(prefix)
            for name in self._discover(prefix, location, verify=level == "city"):
                if name.lower() not in {c.lower() for c, _ in chosen}:
                    chosen.append((name, level))
        return chosen

    def subreddits(self, location: Location) -> list[str]:
        """Where to look: the place's city, region and country subreddits, then the big travel ones."""
        chosen = [name for name, _level in self.geo_subreddits(location)]
        for name in _TRAVEL_SUBREDDITS:
            if name.lower() not in {c.lower() for c in chosen}:
                chosen.append(name)
        return chosen[:_MAX_SUBREDDITS]

    # ------------------------------------------------------------------ the posts
    @staticmethod
    def _wait_for_the_archive() -> bool:
        """Waits out a refusal in progress if it is short; False (skip this request) if it is longer than we will wait."""
        global _BLOCKED_UNTIL
        with _CACHE_LOCK:
            remaining = _BLOCKED_UNTIL - time.monotonic()
        if remaining <= 0:
            return True
        if remaining > _MAX_WAIT_SECONDS:
            return False
        time.sleep(remaining)
        return True

    def _get(self, path: str, params: dict) -> dict | None:
        """One archive request, polite about its limit. A refusal (429 gives the seconds until its window resets; 422 is
        "slow down a bit") is waited out once when short; a long one ends the request, and every request after it until the
        window has passed. None when nothing usable came back."""
        global _BLOCKED_UNTIL
        for attempt in (0, 1):
            if not self._wait_for_the_archive():
                return None
            try:
                response = self._client.get(f"{_BASE}{path}", params=params)
            except httpx.HTTPError:
                return None
            if response.status_code == 200:
                try:
                    body = response.json()
                except ValueError:
                    return None
                return body if isinstance(body, dict) else None
            if response.status_code in (422, 429):
                try:
                    wait = float(response.headers.get("x-ratelimit-reset", _RETRY_AFTER_SECONDS)) if response.status_code == 429 else _RETRY_AFTER_SECONDS
                except ValueError:
                    wait = _RETRY_AFTER_SECONDS
                with _CACHE_LOCK:
                    _BLOCKED_UNTIL = max(_BLOCKED_UNTIL, time.monotonic() + wait + 0.5)
                if attempt == 0:
                    continue
            return None
        return None

    def _posts(self, subreddit: str, term: str) -> list[dict]:
        key = (subreddit.lower(), term)
        with _CACHE_LOCK:
            cached = _POSTS_CACHE.get(key)
        if cached and time.monotonic() - cached[0] < _POSTS_CACHE_TTL_SECONDS:
            return cached[1]
        payload = self._get("/posts/search", {"title": term, "subreddit": subreddit, "limit": _POSTS_PER_REQUEST})
        if payload is None:
            return []
        posts = payload.get("data") or []
        with _CACHE_LOCK:
            _POSTS_CACHE[key] = (time.monotonic(), posts)
        return posts

    @staticmethod
    def _evidence(post: dict, topic_id: str, location: Location) -> Evidence | None:
        title = str(post.get("title") or "").strip()
        permalink = str(post.get("permalink") or "")
        created = post.get("created_utc")
        if not title or not permalink or post.get("over_18"):
            return None
        try:
            published = datetime.fromtimestamp(int(created), tz=timezone.utc) if created is not None else None
        except (TypeError, ValueError, OverflowError, OSError):
            published = None
        body = str(post.get("selftext") or "").strip()
        body = "" if body in _REMOVED else re.sub(r"\s+", " ", body)
        text = f"{title}. {body}".strip()[:_MAX_TEXT_CHARS] if body else title
        return Evidence(
            evidence_id=f"reddit_archive:{topic_id}:{post.get('id')}",
            source_url=f"https://www.reddit.com{permalink}",
            source_title=title,
            publisher="reddit.com",
            source_type=SourceType.COMMUNITY_FORUM,
            retrieved_at=datetime.now(timezone.utc),
            published_at=published,
            location_scope=f"{location.city}, {location.region}",
            text=text,
            topic=topic_id,
            metadata={
                "provider": "reddit_archive",
                "date_source": "reddit_archive",
                "subreddit": str(post.get("subreddit") or ""),
                "score": str(post.get("score") or 0),
                "comments": str(post.get("num_comments") or 0),
            },
        )

    def recent(self, location: Location, days: int, limit: int = 25) -> list[Evidence]:
        """Posts from the last `days` days that are about the area, newest first: what is being said there lately.

        Asked of the archive with a date (`after`), which also makes the request light. In the subreddit named for the
        place's own city (or region, when it has no city) every post counts, that being what the subreddit is; in a wider
        one (the region's, the country's) only a post whose title names the area does. Each has its real posting time.
        Not filtered for the place here: the live feed applies its own area check."""
        area = search_area(location)
        words = [w for w in _name_words(without_admin_prefix(area)) if len(w) >= 4]
        area_term = max(words, key=len) if words else ""
        local_level = "city" if location.city and search_area(location) == without_admin_prefix(location.city) else "region"
        since = datetime.now(timezone.utc) - timedelta(days=days)

        tasks: list[tuple[str, str]] = []
        for name, level in self.geo_subreddits(location):
            if level == local_level:
                tasks.append((name, ""))
            elif area_term:
                tasks.append((name, area_term))
        posts: dict[str, dict] = {}
        pool = ThreadPoolExecutor(max_workers=_WORKERS)
        try:
            futures = [pool.submit(self._recent_posts, sub, term, since, limit) for sub, term in tasks[:4]]
            try:
                for future in as_completed(futures, timeout=self._deadline):
                    for post in future.result():
                        if post.get("id"):
                            posts.setdefault(str(post["id"]), post)
            except TimeoutError:
                pass
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        found: list[Evidence] = []
        for post in posts.values():
            item = self._evidence(post, "live_feed", location)
            if item is None or item.published_at is None or item.published_at < since:
                continue
            # A card shows the post's opening sentences, not the whole text (and nothing where none reads as a sentence).
            item.text = readable_description(str(post.get("selftext") or ""), item.source_title)
            found.append(item)
        newest = sorted(found, key=lambda e: e.published_at, reverse=True)  # type: ignore[arg-type,return-value]
        return newest[:_RECENT_MAX]  # a big city's subreddits would otherwise fill the whole sidebar

    def _recent_posts(self, subreddit: str, term: str, since: datetime, limit: int) -> list[dict]:
        key = (subreddit.lower(), f"recent:{term}:{since.date().isoformat()}")
        with _CACHE_LOCK:
            cached = _POSTS_CACHE.get(key)
        if cached and time.monotonic() - cached[0] < _POSTS_CACHE_TTL_SECONDS:
            return cached[1]
        params: dict = {"subreddit": subreddit, "after": since.date().isoformat(), "sort": "desc", "limit": limit}
        if term:
            params["title"] = term
        payload = self._get("/posts/search", params)
        if payload is None:
            return []
        posts = payload.get("data") or []
        with _CACHE_LOCK:
            _POSTS_CACHE[key] = (time.monotonic(), posts)
        return posts

    def search(self, location: Location, topic: ResearchTopic) -> list[Evidence]:
        area = frozenset(w for text in (location.city, location.region, location.country) if text for w in _name_words(without_admin_prefix(text)))
        terms = search_terms(place_names(location), area)
        if not terms:
            return []
        subreddits = self.subreddits(location)
        # The first term over every subreddit, then the variants' terms, up to the request budget.
        tasks = [(sub, term) for term in terms for sub in subreddits][:_MAX_REQUESTS]

        posts: dict[str, dict] = {}
        pool = ThreadPoolExecutor(max_workers=_WORKERS)
        try:
            futures = [pool.submit(self._posts, sub, term) for sub, term in tasks]
            try:
                for future in as_completed(futures, timeout=self._deadline):
                    for post in future.result():
                        if post.get("id"):
                            posts.setdefault(str(post["id"]), post)
            except TimeoutError:
                pass  # what arrived in time is used; the rest is dropped
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        candidates = [e for e in (self._evidence(p, topic.topic_id, location) for p in posts.values()) if e is not None]
        if self._translator is not None:
            translate_evidence(candidates, self._translator, max_translations=_MAX_TRANSLATIONS)
        return filter_for_place(candidates, location)
