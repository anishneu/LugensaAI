"""Live web search + page retrieval via the Tavily API (Milestone 3).

Requires `TAVILY_API_KEY` (see `app/core/config.py`); nothing here is
imported or constructed unless that key is set (`app/agents/factory.py`
gates it the same way it gates the Milestone 2 LLM components).

Tavily's `include_raw_content=True` returns full extracted page text in the
same search call, so `TavilyPageRetrievalTool` doesn't make a second network
request per result — it just reads from a cache populated by the search
call for the same run, keeping the search-then-retrieve interface without
paying for a second real HTTP request per source.

Real web results don't arrive pre-labeled with a clean `source_type`.
`_classify_source_type()` is a coarse, honest
best-effort heuristic based on the domain — not a real classifier — and
defaults to `SourceType.OTHER` rather than guessing a specific wrong type.

Real results also arrive as messy raw text — markdown image/link syntax,
heading hashes, video chapter timestamps, nav boilerplate. `_clean_text()`
strips the obvious noise; it's a cleanup pass, not a summarizer, so it can
still leave imperfect text behind.

Three filters run on every result, all as a soft filter — if applying them
would drop every candidate for a topic, nothing is dropped, since a topic
with zero evidence and a coverage-gap limitation is more honest than one
that silently swaps in a bad result to avoid looking empty:
- A minimum cleaned-length check drops results that had almost nothing left
  after cleaning (e.g. a video whose "content" was mostly chapter markers).
- `_is_relevant_to_location()` drops results whose title/text never
  mentions the place by name, a real (if blunt) defense against generic
  regional content masquerading as being about the specific location asked
  about.
- Images come from Tavily's `include_images` and are attached to results by
  position — Tavily does not guarantee a given image depicts that specific
  result, so this is best-effort, not a claim of exact attribution.

Live search evidence only turns into claims when a language model is configured
(`LLMClaimExtractor`); without one the response shows the sources and says no
claims were extracted — see `backend/README.md`.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from app.models.evidence import Evidence, SourceType
from app.models.location import Location
from app.models.plan import ResearchTopic
from app.tools.base import PageRetrievalTool, ToolConfigurationError, ToolExecutionError, WebSearchTool
from app.tools.translation import META_ORIGINAL_TEXT, META_ORIGINAL_TITLE, Translator, translate_evidence

# Government and university sites are not just `.gov` / `.edu`: Japan uses go.jp and lg.jp (local
# government), the UK gov.uk and ac.uk, France gouv.fr, Mexico gob.mx, Korea go.kr, India nic.in and
# gov.in, Australia gov.au and edu.au, Brazil gov.br. Classifying only the US ones left every other
# country's official sources scored as "other" and weighted at 0.4 instead of 0.9.
_GOV_TLDS = (".gov", "europa.eu", "un.org", "who.int", "worldbank.org")
_EDU_TLDS = (".edu",)
_GOV_SLD_RE = re.compile(r"(?:^|\.)(?:gov|gob|gouv|govt|go|gv|gc|lg|nic|gub|gouv)\.[a-z]{2}$")
_EDU_SLD_RE = re.compile(r"(?:^|\.)(?:edu|ac)\.[a-z]{2}$")
_FORUM_DOMAINS = ("reddit.com", "quora.com", "nextdoor.com")
_REVIEW_DOMAINS = (
    "yelp.com", "tripadvisor.", "zillow.com", "apartments.com", "google.com/maps", "tabelog.com", "retty.me",
    "gurunavi.com", "hotpepper.jp", "booking.com", "agoda.com", "trip.com", "zomato.com", "foursquare.com",
    "opentable.com", "thefork.", "dianping.com", "naver.com/", "kakao.com", "wongnai.com", "map.yahoo.co.jp",
)
_BLOG_DOMAINS = ("medium.com", "substack.com", "blogspot.com")

_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HEADING_RE = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_TIMESTAMP_LINE_RE = re.compile(r"^\s*\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s.*$", re.MULTILINE)
_APP_STORE_LINE_RE = re.compile(r"^.*(app-store|play\.google\.com|Get our ?App).*$", re.MULTILINE | re.IGNORECASE)
_NAV_MENU_LINE_RE = re.compile(r"^(?:[^\n|]*\|){3,}[^\n]*$", re.MULTILINE)
_BULLET_NAV_BLOCK_RE = re.compile(r"(?:^[ \t]*[*•]\s.{0,60}$\n?){3,}", re.MULTILINE)
# Travel/review-aggregator breadcrumb nav (TripAdvisor and similar) — a line
# naming several of these categories together is never real review content,
# regardless of exact spacing/concatenation from how the page was scraped
# (e.g. "BostonThings to DoHotelsRestaurantsCruisesForums").
_TRAVEL_NAV_KEYWORD = r"(?:Things to Do|Hotels?|Restaurants?|Cruises?|Forums?|Vacation Rentals?|Flights?|Vacation Packages?)"
_TRAVEL_NAV_LINE_RE = re.compile(rf"^.*(?:{_TRAVEL_NAV_KEYWORD}.*){{3,}}$", re.MULTILINE)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
# Markdown-converting extractors emit backslash escapes that
# survive as stray "\ \" once the markup around them is stripped. Only runs
# of backslashes standing alone between whitespace are removed, so an escape
# inside a word is left intact.
_STRAY_ESCAPE_RE = re.compile(r"(?<!\S)\\+(?!\S)")
# Accessibility skip-links. These are whole lines in some extracts and run
# together inline in others ("Skip navigation Skip to main content"), so the
# exact-line denylist below can't catch them on its own. Safe to strip
# anywhere: no real prose contains them.
_SKIP_LINK_RE = re.compile(r"\bskip (?:to (?:main )?content|navigation)\b", re.IGNORECASE)

# Exact-match, case-insensitive: known UI chrome from specific platforms
# (Facebook, Nextdoor, Zillow, TripAdvisor, ...) observed in real scraped
# results. A denylist of known junk lines, rather than a generic "short
# line" filter — a generic filter would also gut legitimate short-line
# content like a crime-statistics table (numbers and place names are short
# lines too, and those are exactly the kind of safety data this project
# wants surfaced).
_KNOWN_UI_JUNK_LINES = {
    "log in",
    "forgot account?",
    "video home",
    "live reels",
    "explore more",
    "explore video",
    "sign up",
    "sign in",
    "create new account",
    "see more",
    "where is this data from?",
    "don't miss out!",
    "see what verified neighbors are saying",
    "loadingloading...",
    "total monthly price",
    "skip to main content",
    "plan with ai",
    "rewards",
    "discover",
    "review",
    "usd",
    "skip navigation",
    "your browser is not supported for this experience.",
    "we recommend using chrome, firefox, edge, or safari.",
    "accessibility in boston",
    "share",
    "share on facebook",
    "share on twitter",
    "share on linkedin",
}

# How far back the live feed looks. Also the window named in the UI, so the
# feed never implies more coverage than it actually searched.
LIVE_FEED_WINDOW_DAYS = 7

# Tavily's news topic returns roughly 8-9 results for a single regional query
# in a 7-day window regardless of `max_results`, which isn't enough to fill
# the feed. These complementary facets are issued as separate searches and
# merged: measured against the live API they yielded 25 unique dated items
# for one city where the first alone yielded 8. They also give the feed
# actual topical spread (reporting, incidents, civic/community activity)
# instead of three pages of the same beat.
#
# Each facet is one real, billed Tavily search per feed load — this constant
# is the main cost knob for this surface. See `backend/README.md`.
_LIVE_FEED_FACETS = (
    "local news",
    "police incident report",
    "community events development",
)

# Job listings match a regional news query (a company's careers page names
# the city its office is in) and carry a real posted date, so neither the
# date requirement nor the locality check rejects them — but a role opening
# at a company that happens to sit in this city is not "what's happening
# around here". Matched against the URL's host/path, not page text, so a
# news story *about* local hiring still gets through.
_NON_ACTIVITY_URL_PATTERNS = ("jobs.", "careers.", "/jobs/", "/job/", "/careers/")

_MIN_USABLE_SNIPPET_LENGTH = 40
_MAX_DISPLAY_LENGTH = 1200
_MAX_FULL_TEXT_LENGTH = 3000
# Translation runs on the CPU and is slow (see app/tools/translation.py), so cap it per search call.
_MAX_TRANSLATIONS_PER_SEARCH = 6


_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")


def _effective_length(text: str) -> int:
    """Length as English-equivalent characters. One Japanese/Chinese/Korean
    character carries roughly what three Latin ones do, so a plain `len()` would
    throw away short-but-complete CJK passages as "too short to be useful"."""
    return len(text) + 2 * len(_CJK_RE.findall(text))


def _drop_known_junk_lines(text: str) -> str:
    lines = [line for line in text.split("\n") if line.strip().lower() not in _KNOWN_UI_JUNK_LINES]
    return "\n".join(lines)


def _deduplicate_paragraphs(text: str) -> str:
    """Drop repeated paragraphs, keeping the first occurrence.

    Real scraped pages — Nextdoor and similar dynamic sites especially —
    sometimes render the same block of text twice (once in a card, once in
    an "expanded" or "related" section). This is deduplication, not
    summarization: paragraphs are compared for exact equality, nothing is
    reworded or shortened.
    """
    seen: set[str] = set()
    kept = []
    for paragraph in text.split("\n\n"):
        normalized = paragraph.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        kept.append(paragraph)
    return "\n\n".join(kept)


def _clean_text(text: str) -> str:
    """Strip markdown/boilerplate noise a raw web-scrape carries.

    Intentionally conservative: it removes syntax and clearly-junk lines
    (image tags, link brackets, heading hashes, video chapter timestamps,
    app-store nag lines, "Home | About | Contact"-style nav menus, known UI
    chrome strings, exact-duplicate paragraphs) but does not attempt real
    summarization or paraphrasing — what's left is still the source's own
    words, just without the noise around them.
    """
    cleaned = _MD_IMAGE_RE.sub("", text)
    # Unwrap links to their link text *before* the nav-detection passes below —
    # otherwise a bulleted nav link like "*   [Help Center](https://...)" keeps
    # its long raw URL and never looks short enough to be recognized as nav.
    cleaned = _MD_LINK_RE.sub(r"\1", cleaned)
    cleaned = _NAV_MENU_LINE_RE.sub("", cleaned)
    cleaned = _BULLET_NAV_BLOCK_RE.sub("", cleaned)
    cleaned = _TRAVEL_NAV_LINE_RE.sub("", cleaned)
    cleaned = _HEADING_RE.sub("", cleaned)
    cleaned = _TIMESTAMP_LINE_RE.sub("", cleaned)
    cleaned = _APP_STORE_LINE_RE.sub("", cleaned)
    cleaned = _SKIP_LINK_RE.sub("", cleaned)
    cleaned = _STRAY_ESCAPE_RE.sub("", cleaned)
    cleaned = _drop_known_junk_lines(cleaned)
    cleaned = _MULTI_SPACE_RE.sub(" ", cleaned)
    cleaned = _MULTI_BLANK_RE.sub("\n\n", cleaned)
    cleaned = _deduplicate_paragraphs(cleaned)
    return cleaned.strip()


def _truncate_for_display(text: str, limit: int = _MAX_DISPLAY_LENGTH) -> str:
    """Cap how much of a cleaned passage is shown/scored.

    Real scraped pages can stay long even after cleaning (repeated
    boilerplate, multiple stacked snippets). Capping keeps evidence
    readable; the full text is still reachable via the source link and,
    separately, via `raw_content_cache` for anything that wants it uncut.
    """
    if len(text) <= limit:
        return text
    truncated = text[:limit].rsplit(" ", 1)[0]
    return truncated.rstrip(".,;: ") + "…"


def _is_relevant_to_location(item_text: str, location: Location) -> bool:
    haystack = item_text.lower()
    needles = [location.name.lower()]
    if location.city:
        needles.append(location.city.lower())
    # Native-script names: a page that survived translation may still spell the place its own way.
    needles += [n.lower() for n in (location.local_name, location.local_area) if n]
    return any(needle in haystack for needle in needles if needle)


# Words that describe *what kind of place* something is, not *which* place.
# "LEAVES Coffee Roasters" shares "coffee" and "roasters" with "SR Coffee
# Roaster & Bar", so matching on them is how one cafe's reviews end up cited
# for another. Only what's left (here: "sr") identifies the business.
_GENERIC_NAME_WORDS = frozenset(
    """the and of a an at in on by for cafe cafes coffee coffees roaster roasters roastery bar bars pub
    restaurant restaurants hotel hotels inn hostel shop shops store stores house kitchen grill bistro
    bakery market club lounge tavern diner eatery gallery studio salon spa gym""".split()
)
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _name_words(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text.replace("'", "").replace("’", ""))]


def _mentions_business(text: str, business_name: str) -> bool:
    """Whether `text` is actually about this one business.

    A business needs a much stricter test than an area: its city appearing on
    the page proves nothing (every cafe in Tokyo is "in Tokyo"). Every
    *distinguishing* word of its name must appear; if the name has none
    (just "Coffee Shop"), the whole name must appear as a phrase.
    """
    name_words = _name_words(business_name)
    if not name_words:
        return False
    text_words = _name_words(text)
    text_set = set(text_words)

    distinctive = [w for w in name_words if w not in _GENERIC_NAME_WORDS]
    if distinctive:
        return all(w in text_set for w in distinctive)

    phrase = " ".join(name_words)
    return phrase in " ".join(text_words)


def _mentions_place_context(text: str, location: Location) -> bool:
    """Whether `text` places the business in the right part of the world.

    The business name alone isn't enough: "SR Coffee" is also a cafe in
    Leesburg, Virginia, and its Yelp page matched on the name. The page must
    also name the city or region (or, failing both, the country). If the
    location carries none of those, there is nothing to check against.
    """
    anchors = [a for a in (location.city, location.region) if a] or [a for a in (location.country,) if a]
    if not anchors:
        return True
    # The city as its own people write it ("久留米市"): no spaces in that script, so a plain substring test.
    if location.local_area and location.local_area in text:
        return True
    words = set(_name_words(text))
    return any(all(w in words for w in _name_words(anchor)) for anchor in anchors)


def _is_about_business(text: str, location: Location) -> bool:
    """`_mentions_business` for the English name, or the native-script name ("翠藍") that a local
    page uses even after translation renders it differently."""
    if _mentions_business(text, location.name):
        return True
    return bool(location.local_name) and location.local_name in text


def _region_label(location: Location) -> str:
    """The broader area the live feed reports on -- dynamically derived
    from whatever location was selected, never hardcoded to one city. A
    POI's own city/region if known; only a bare place name (no city/region
    at all) falls back to its own name, since there's nothing broader to
    anchor on."""
    return ", ".join(filter(None, [location.city, location.region])) or location.name


def _region_anchor(location: Location) -> str:
    return (location.city or location.region or location.name).lower()


def _is_non_activity_url(url: str) -> bool:
    parsed = urlparse(url.lower())
    target = f"{parsed.netloc}{parsed.path}"
    return any(pattern in target for pattern in _NON_ACTIVITY_URL_PATTERNS)


def _mentions_whole_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word.lower())}\b", text.lower()) is not None


def _is_relevant_to_live_feed(title: str, body: str, location: Location, source: str = "") -> bool:
    """The live feed surfaces recent regional activity -- a news article, a
    local announcement, an incident report -- rather than coverage of one
    exact business, so the anchor is always the area (city, or region if no
    city is known), never a specific POI's name.

    `source` (the result's URL + publisher) carries signal the title doesn't,
    and the two are weighted differently because city names are not unique:

    - A *hyper-local outlet* -- one whose own domain carries the city name,
      like `cambridgema.gov` or `cambridgeday.com` -- is accepted outright.
      These are the most local sources there are, and they rarely bother
      naming their own state, so any rule that demands one drops exactly the
      coverage most worth showing.
    - Anything else must name the city *and* the surrounding region/state
      somewhere. Measured against the live API, a query for Cambridge, MA
      surfaced a New York State Police report -- there is also a Cambridge,
      New York -- and this is what rejects it.

    The tradeoff is real and chosen deliberately: a regional outlet that
    names the city but never its state (a university paper covering the city
    it sits in, say) is dropped too. For a feed with no downstream
    verification, a wrong-state item is worse than a missing one.
    """
    city = _region_anchor(location)
    if not city:
        return True

    haystack = f"{title} {body}".lower()
    source_text = source.lower()

    if city in source_text:
        return True

    names_city = _mentions_whole_word(haystack, city) or haystack.count(city) >= 2
    if not names_city:
        return False

    region = (location.region or "").strip()
    if not region:
        # Nothing broader to disambiguate against; fall back to requiring the
        # city in the headline or repeated in the body.
        return city in title.lower() or haystack.count(city) >= 2

    return _mentions_whole_word(f"{haystack} {source_text}", region)



# Recovers a real date from page text for sources whose search API result
# never carries a structured `published_date` but whose scraped text does --
# measured against the live API, TripAdvisor's own raw_content includes a
# plain "Reviewed <Month> <Day>, <Year>" line per review even though its API
# field is always null. Deliberately narrow (an explicit "Reviewed"/"Posted"
# phrase, not any bare date-shaped number on the page): a wrong date is worse
# than an honestly-missing one for a feature whose whole point is "when this
# was actually posted".
_TEXT_DATE_RE = re.compile(
    r"\b(?:reviewed|posted)\s+(?:on\s+)?"
    r"(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})",
    re.IGNORECASE,
)


def _extract_published_date_from_text(text: str) -> datetime | None:
    if not text:
        return None
    match = _TEXT_DATE_RE.search(text)
    if not match:
        return None
    try:
        parsed = datetime.strptime(f"{match['month']} {match['day']} {match['year']}", "%B %d %Y")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


def _is_relevant_to_community_voice(title: str, body: str, location: Location, source: str = "") -> bool:
    """Community Voices shows real forum/review commentary about the exact
    selected place, so it needs a tighter check than the soft per-topic
    relevance filter every other topic uses: a bare city name isn't proof of
    the right place -- city names collide across states (the live feed hit
    this with a Cambridge, NY report surfacing for a Cambridge, MA query; see
    `_is_relevant_to_live_feed`), and a chain POI's own name doesn't
    disambiguate branches (see `starbucks_cambridge` in tests) -- a review
    site's "nearby places" carousel can surface an unrelated same-named
    place, or the same chain in a different city, just as easily.

    A *distinctive* (multi-word) place name mentioned by name is trusted on
    its own, the same way a hyper-local domain is trusted for the live feed
    -- it doesn't need a city restated alongside it. Short of that, city (or
    a hyper-local domain) is required, and region strengthens it further; a
    single generic word like "Starbucks" mentioned near a bare city name
    isn't enough on its own, since that doesn't meaningfully narrow which
    branch a comment is actually about.
    """
    haystack = f"{title} {body}".lower()
    source_text = source.lower()
    name = (location.name or "").strip().lower()

    if len(name.split()) > 1 and _mentions_whole_word(haystack, name):
        return True
    # Native-script names have no word boundaries, so match them as plain substrings.
    if location.local_name and location.local_name.lower() in haystack:
        return True
    if location.local_area and location.local_area.lower() in haystack:
        return True

    city = _region_anchor(location)
    if not city:
        return bool(name) and _mentions_whole_word(haystack, name)

    if city in source_text:
        return True
    if not _mentions_whole_word(haystack, city):
        return False

    region = (location.region or "").strip()
    if not region:
        return True
    return _mentions_whole_word(f"{haystack} {source_text}", region)


def _classify_source_type(url: str) -> SourceType:
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    if domain.endswith(_GOV_TLDS) or _GOV_SLD_RE.search(domain):
        return SourceType.LOCAL_GOVERNMENT
    if domain.endswith(_EDU_TLDS) or _EDU_SLD_RE.search(domain):
        return SourceType.ACADEMIC
    if any(d in domain for d in _FORUM_DOMAINS):
        return SourceType.COMMUNITY_FORUM
    if any(d in url.lower() for d in _REVIEW_DOMAINS):
        return SourceType.REVIEW_AGGREGATOR
    if any(d in domain for d in _BLOG_DOMAINS):
        return SourceType.BLOG
    return SourceType.OTHER


def _parse_published_date(value: object) -> datetime | None:
    """Parse a publication date into a timezone-aware UTC datetime.

    Tavily returns dates in more than one shape — bare ISO dates from the
    general topic, RFC-2822 from the news topic — and a naive datetime mixed
    in with aware ones is not merely untidy: comparing the two raises
    TypeError, which would take down any sort over a feed containing both.
    A date with no zone is read as UTC rather than dropped.
    """
    if not value or not isinstance(value, str):
        return None

    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None

    if parsed is None:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _evidence_id(topic_id: str, url: str) -> str:
    return f"tavily:{topic_id}:{hashlib.sha1(url.encode('utf-8')).hexdigest()[:12]}"


def _extract_image_url(raw_image: object) -> str | None:
    if isinstance(raw_image, str):
        return raw_image
    if isinstance(raw_image, dict):
        url = raw_image.get("url")
        return url if isinstance(url, str) else None
    return None


def _build_candidates(
    location: Location, topic_id: str, results: list[dict], images: list, cache: dict[str, str]
) -> list[Evidence]:
    """Turn raw Tavily results into Evidence — shared by the per-topic
    research search and the topic-agnostic live feed, so cleaning/length
    filtering/image-pairing logic exists in exactly one place."""
    candidates: list[Evidence] = []
    for index, item in enumerate(results):
        url = item.get("url")
        if not url:
            continue
        raw_content = _truncate_for_display(_clean_text(item.get("raw_content") or ""), _MAX_FULL_TEXT_LENGTH)
        snippet = _truncate_for_display(_clean_text(item.get("content") or raw_content[:500]))
        title = item.get("title") or url

        if _effective_length(snippet) < _MIN_USABLE_SNIPPET_LENGTH:
            # Cleaning (stripping nav menus, timestamps, markdown) can leave
            # almost nothing behind for some sources (e.g. a video whose
            # "content" was mostly chapter markers) — not worth keeping.
            continue

        # Tavily's own `published_date` field is null for entire classes of
        # source (measured live: every Reddit, Yelp, and TripAdvisor result)
        # even when the scraped page text names a real date in plain English
        # ("Reviewed July 30, 2016" on TripAdvisor) — recover that before
        # giving up on a real timestamp for this item.
        published_at = _parse_published_date(item.get("published_date"))
        if published_at is None:
            published_at = _extract_published_date_from_text(raw_content) or _extract_published_date_from_text(
                snippet
            )

        cache[url] = raw_content or snippet
        candidates.append(
            Evidence(
                evidence_id=_evidence_id(topic_id, url),
                source_url=url,
                source_title=title,
                publisher=urlparse(url).netloc.removeprefix("www.") or None,
                source_type=_classify_source_type(url),
                retrieved_at=datetime.now(timezone.utc),
                published_at=published_at,
                location_scope=f"{location.city}, {location.region}",
                text=snippet,
                topic=topic_id,
                metadata={"provider": "tavily"},
                image_url=_extract_image_url(images[index]) if index < len(images) else None,
            )
        )
    return candidates


class TavilyWebSearchTool(WebSearchTool):
    def __init__(
        self,
        api_key: str | None = None,
        max_results: int = 4,
        client: object | None = None,
        translator: Translator | None = None,
    ) -> None:
        self.raw_content_cache: dict[str, str] = {}
        self._max_results = max_results
        self._translator = translator

        if client is not None:
            self._client = client
            return

        if not api_key:
            raise ToolConfigurationError("TavilyWebSearchTool requires an api_key (TAVILY_API_KEY).")
        try:
            from tavily import TavilyClient
        except ImportError as exc:
            raise ToolConfigurationError(
                "The 'tavily-python' package is required. Install it with `pip install tavily-python` "
                "(already in requirements.txt)."
            ) from exc
        self._client = TavilyClient(api_key=api_key)

    def _worth_translating(self, location: Location):
        """A predicate for `translate_evidence`, or None to translate everything (up to the cap).

        With the place's native-script names known, a foreign page is worth translating only if it
        mentions the place, its city, or the English name, checked on the original text. Without native
        names nothing can be checked before translating, so nothing is skipped.
        """
        if not (location.local_name or location.local_area):
            return None
        needles = [n.lower() for n in (location.name, location.city, location.local_name, location.local_area) if n]

        def worth(item: Evidence) -> bool:
            haystack = f"{item.source_title} {item.text} {item.source_url} {self.raw_content_cache.get(item.source_url, '')}".lower()
            return any(needle in haystack for needle in needles)

        return worth

    def search(self, location: Location, topic: ResearchTopic) -> list[Evidence]:
        location_label = f"{location.name}, {location.city}, {location.region}".strip(", ")
        query = topic.search_queries[0] if topic.search_queries else f"{location_label} {topic.topic_id}"
        # The English query plus, for a place in a non-English-speaking country, one in its own language.
        queries = [query, *topic.local_queries[:1]]

        results: list = []
        images: list = []
        seen_urls: set[str] = set()
        failures: list[str] = []
        for text in queries:
            try:
                response = self._client.search(
                    query=text,
                    max_results=self._max_results,
                    include_raw_content=True,
                    include_images=True,
                )
            except Exception as exc:  # noqa: BLE001 - the Tavily SDK's own exception types aren't guaranteed
                failures.append(f"Tavily search failed for query '{text}': {exc}")
                continue
            if not isinstance(response, dict):
                continue
            for result in response.get("results", []):
                url = result.get("url") if isinstance(result, dict) else None
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                results.append(result)
            images.extend(response.get("images", []))
        if failures and len(failures) == len(queries):
            raise ToolExecutionError(failures[0])

        candidates = _build_candidates(location, topic.topic_id, results, images, self.raw_content_cache)
        if self._translator is not None:
            # Before the relevance filters below: a Japanese page about the
            # place doesn't spell its name the way the English query does,
            # and would otherwise be judged off-topic on words it never used.
            translate_evidence(
                candidates,
                self._translator,
                max_translations=_MAX_TRANSLATIONS_PER_SEARCH,
                should_translate=self._worth_translating(location),
            )
        if location.is_business:
            # One specific business: a page either mentions it or it isn't
            # evidence about it. No soft fallback here — unlike an area, where
            # a nearby-but-imperfect page is still informative, another
            # business's reviews are actively misleading, so an honest
            # "nothing found" beats them.
            about_this_business = []
            for c in candidates:
                haystack = (
                    f"{c.source_title} {c.text} {c.source_url} {self.raw_content_cache.get(c.source_url, '')} "
                    f"{c.metadata.get(META_ORIGINAL_TITLE, '')} {c.metadata.get(META_ORIGINAL_TEXT, '')}"
                )
                if _is_about_business(haystack, location) and _mentions_place_context(haystack, location):
                    about_this_business.append(c)
            return about_this_business

        relevant = [
            c
            for c in candidates
            if _is_relevant_to_location(
                f"{c.source_title} {c.text} {c.metadata.get(META_ORIGINAL_TITLE, '')} "
                f"{c.metadata.get(META_ORIGINAL_TEXT, '')}",
                location,
            )
        ]

        # Soft filter: an empty topic with an honest coverage-gap limitation
        # is more honest than quietly keeping off-topic results to avoid it,
        # but dropping every single candidate (e.g. the location name
        # appears only in the query, never in any real result) is worse than
        # showing the unfiltered results, clearly flagged as such.
        if relevant:
            result = relevant
        else:
            for candidate in candidates:
                candidate.metadata["location_match"] = "false"
            result = candidates

        # Community Voices (frontend) reads forum/review evidence straight
        # out of the research response, with no verification step downstream
        # to catch a wrong-place match the way claim extraction does for
        # everything else — so unlike the soft filter above, a forum/review
        # result that fails the stricter place check is dropped outright
        # rather than shown flagged. See `_is_relevant_to_community_voice`.
        return [
            c
            for c in result
            if c.source_type not in (SourceType.COMMUNITY_FORUM, SourceType.REVIEW_AGGREGATOR)
            or _is_relevant_to_community_voice(
                c.source_title,
                f"{c.text} {c.metadata.get(META_ORIGINAL_TEXT, '')}",
                location,
                f"{c.source_url} {c.publisher or ''}",
            )
        ]


class TavilyLiveFeedTool:
    """Recency-biased, topic-agnostic search: "what's happening recently in
    this broader region" — deliberately independent of both the specific
    selected place and any specific research question. A POI like one
    Starbucks branch rarely has anything published about it by name in the
    last week, and the point of this feed (unlike the Community tab, which
    is about the exact selected place) is regional awareness, not coverage
    of one business — so every query and relevance check here is anchored
    on the area (city, or region if no city is known), never the place's own
    name.

    Searches Tavily's *news* topic, not its general topic. Measured against
    the live API, the general topic returned `published_date: None` for
    every result and surfaced mostly evergreen landing pages (a paper's
    `/tag/local-news` index, a chamber-of-commerce homepage); the news topic
    returns real RFC-2822 timestamps on real articles. Since this feed's
    entire claim is recency, that difference decides both what it can honestly
    display and what's worth displaying at all.

    Not part of the verified research pipeline: no per-topic planning, no
    claim extraction, no verification. `topic="live_feed"` on the resulting
    Evidence is a label for consistent typing, not a real research topic.
    Every call is a real, billed Tavily search — see `backend/README.md`
    before wiring this up to an aggressive auto-refresh interval.
    """

    def __init__(
        self,
        api_key: str | None = None,
        max_results: int = 20,
        client: object | None = None,
        translator: Translator | None = None,
    ) -> None:
        self.raw_content_cache: dict[str, str] = {}
        self._max_results = max_results
        self._translator = translator

        if client is not None:
            self._client = client
            return

        if not api_key:
            raise ToolConfigurationError("TavilyLiveFeedTool requires an api_key (TAVILY_API_KEY).")
        try:
            from tavily import TavilyClient
        except ImportError as exc:
            raise ToolConfigurationError(
                "The 'tavily-python' package is required. Install it with `pip install tavily-python` "
                "(already in requirements.txt)."
            ) from exc
        self._client = TavilyClient(api_key=api_key)

    def fetch(self, location: Location) -> list[Evidence]:
        region_label = _region_label(location)

        candidates: list[Evidence] = []
        failures: list[str] = []
        for facet in _LIVE_FEED_FACETS:
            query = f"{region_label} {facet}"
            try:
                response = self._client.search(
                    query=query,
                    max_results=self._max_results,
                    topic="news",
                    days=LIVE_FEED_WINDOW_DAYS,
                    include_raw_content=True,
                    include_images=True,
                )
            except Exception as exc:  # noqa: BLE001 - the Tavily SDK's own exception types aren't guaranteed
                # One facet failing shouldn't blank the whole feed — collect
                # it and only surface an error if every facet failed.
                failures.append(f"'{query}': {exc}")
                continue

            results = response.get("results", []) if isinstance(response, dict) else []
            images = response.get("images", []) if isinstance(response, dict) else []
            candidates.extend(_build_candidates(location, "live_feed", results, images, self.raw_content_cache))

        if failures and len(failures) == len(_LIVE_FEED_FACETS):
            raise ToolExecutionError("Tavily live-feed search failed for every query — " + "; ".join(failures))

        # A feed item without a real publication timestamp is dropped, not
        # backfilled with the time we happened to fetch it. Two reasons, and
        # the second is why this filter does double duty:
        #   1. The feed's whole claim is recency. Showing "just now" for
        #      something whose actual post time is unknown is a fabricated
        #      timestamp, which this project doesn't do.
        #   2. Undated results are overwhelmingly evergreen directory and
        #      landing pages ("Community Events in <city>", a paper's
        #      /tag/local-news index) rather than actual posts — measured
        #      against the live API, Tavily's general topic returned a null
        #      published_date for *every* result, while its news topic
        #      returns real RFC-2822 timestamps on real articles. Requiring
        #      a date is therefore also the quality filter.
        dated = [
            c
            for c in candidates
            if c.published_at is not None and not _is_non_activity_url(c.source_url)
        ]

        dated.sort(key=lambda e: e.published_at, reverse=True)
        if self._translator is not None:
            # Newest first, so if there are more foreign items than the
            # translation cap, it's the oldest that stay untranslated.
            translate_evidence(dated, self._translator, max_translations=_MAX_TRANSLATIONS_PER_SEARCH)

        # Unlike per-topic research search, there's no verified pipeline
        # downstream to catch an overly loose match, so the location filter
        # here is not soft: a result with no regional signal is dropped
        # outright rather than shown with a caveat.
        relevant = [
            c
            for c in dated
            if _is_relevant_to_live_feed(c.source_title, c.text, location, f"{c.source_url} {c.publisher or ''}")
        ]

        seen_urls: set[str] = set()
        deduplicated: list[Evidence] = []
        for item in relevant:
            if item.source_url in seen_urls:
                continue
            seen_urls.add(item.source_url)
            deduplicated.append(item)

        deduplicated.sort(key=lambda e: e.published_at, reverse=True)
        return deduplicated


class TavilyPageRetrievalTool(PageRetrievalTool):
    """Reads full text from the cache a `TavilyWebSearchTool` populated during search.

    Must be constructed with the same cache dict as the search tool used in
    the same run (see `app/agents/factory.py`) — it makes no network calls
    of its own.
    """

    def __init__(self, raw_content_cache: dict[str, str]) -> None:
        self._cache = raw_content_cache

    def retrieve_full_text(self, source_url: str) -> str | None:
        return self._cache.get(source_url) or None
