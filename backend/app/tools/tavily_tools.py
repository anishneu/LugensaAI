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
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from app.models.evidence import Evidence, SourceType
from app.models.location import Location
from app.models.plan import ResearchTopic
from app.tools.base import PageRetrievalTool, ToolConfigurationError, ToolExecutionError, WebSearchTool
from app.tools.community_sources import feed_domains, is_community_domain
from app.tools.descriptions import readable_description
from app.tools.post_dates import PostDateRecovery
from app.tools.translation import (
    META_ORIGINAL_TEXT,
    META_ORIGINAL_TITLE,
    META_TRANSLATED_BY,
    Translator,
    translate_evidence,
)

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
    "opentable.com", "thefork.", "dianping.com", "map.naver.com", "kakao.com", "wongnai.com", "map.yahoo.co.jp",
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
# How far back "recent" reaches. Seven days was too tight: a village, or a whole country's general
# coverage, often has nothing in a week, and a feed that is empty most of the time is not a feed.
LIVE_FEED_WINDOW_DAYS = 30

# The feed is about the place's own city and, if that is too thin, the wider region around it (Xinyi District,
# then Taipei City). It never widens to the whole country: that pulled in stories that were about Taiwan and
# not about Taipei, and each extra scope is more billed searches. Only a place with no city or region at all
# (a country itself, or a bare name) is searched as itself.
#
# Widening happens when the exact area yields fewer than this many items in total (news and community
# together: community posts from one district are sparse by nature, so they alone must not trigger it).
_FEED_MIN_ITEMS = 6
# When widening, a kind that already has this many items is not searched again at the wider scope.
_FEED_MIN_PER_KIND = 3

# A feed load costs real Tavily credits (the free plan is 1,000 a month, shared with every research
# question), so it is kept as cheap as it can be while still being useful:
#   * at most 2 scopes x 2 kinds = 4 basic searches, and usually 2 (one news, one community);
#   * the whole feed is cached per place, and each scope's search per city, so a second place in the same
#     city, a re-opened tab or a React dev-mode double load costs nothing;
#   * a scope's search is cached for an hour, the same as the feed.
_FEED_CACHE_TTL_SECONDS = 60 * 60
_FEED_CACHE: dict[tuple, tuple[float, list[Evidence]]] = {}
_FEED_CACHE_LOCK = threading.Lock()
_SCOPE_CACHE: dict[tuple, tuple[float, list[Evidence]]] = {}
_FEED_INFLIGHT: dict[tuple, threading.Lock] = {}

# One search per kind per scope. Tavily's news topic returns only ~7-9 results, so a second "facet" query
# used to be issued to widen it; that doubled the news cost for a modest gain, and one query that names both
# news and events gets most of it. The words differ by scope: a whole country has no "local news".
_NEWS_QUERY_LOCAL = "local news and events"
_NEWS_QUERY_GENERAL = "news travel culture events"
# Forums, Reddit, Quora and regional communities. Undated, and kept: see community_sources.py.
_COMMUNITY_FACET = "living and visiting: what is it like"

# Job listings match a regional news query (a company's careers page names
# the city its office is in) and carry a real posted date, so neither the
# date requirement nor the locality check rejects them — but a role opening
# at a company that happens to sit in this city is not "what's happening
# around here". Matched against the URL's host/path, not page text, so a
# news story *about* local hiring still gets through.
_NON_ACTIVITY_URL_PATTERNS = ("jobs.", "careers.", "/jobs/", "/job/", "/careers/")

# Posts and pages whose date the search API omits but the source states somewhere (see post_dates.py).
_DATED_SOURCE_TYPES = (SourceType.COMMUNITY_FORUM, SourceType.REVIEW_AGGREGATOR, SourceType.BLOG)

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
    city_forms = _name_forms(city)

    if any(form in source_text for form in city_forms):
        return True

    names_city = any(_mentions_whole_word(haystack, form) or haystack.count(form) >= 2 for form in city_forms)
    if not names_city:
        return False

    region = (location.region or "").strip()
    if not region:
        # Nothing broader to disambiguate against; fall back to requiring the
        # city in the headline or repeated in the body.
        return any(form in title.lower() or haystack.count(form) >= 2 for form in city_forms)

    return any(_mentions_whole_word(f"{haystack} {source_text}", form) for form in _name_forms(region))


# "Taipei City" is written "Taipei" by the people who post there (r/Taipei, "Areas to live in Taipei"), and
# "Xinyi District" is "Xinyi". Requiring the administrative word too discarded nearly every Reddit thread,
# so a name is also accepted without its trailing "City", "District", and so on. The region check that
# follows still has to be met, which is what keeps a Cambridge, New York report out of a Cambridge, MA feed.
_GENERIC_SUFFIXES = {"city", "district", "county", "province", "prefecture", "municipality", "borough", "ward"}


def _name_forms(name: str) -> list[str]:
    parts = name.lower().split()
    forms = [" ".join(parts)]
    if len(parts) > 1 and parts[-1] in _GENERIC_SUFFIXES:
        forms.append(" ".join(parts[:-1]))
    return forms


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
    if is_community_domain(domain):  # after the review check: Tabelog and Yelp are on the list but are review sites
        return SourceType.COMMUNITY_FORUM
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
    location: Location, topic_id: str, results: list[dict], images: list, cache: dict[str, str], describe: bool = False
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

        # For display in a feed card: whole sentences, not the page's markup and chrome (see descriptions.py).
        description = readable_description(item.get("content") or item.get("raw_content") or "", title) if describe else ""

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
                metadata={"provider": "tavily", **({"description": description} if describe else {})},
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
        include_domains_for: Callable[[Location], list[str]] | None = None,
        raw_content_cache: dict[str, str] | None = None,
        date_recovery: PostDateRecovery | None = None,
    ) -> None:
        # Shared with the page-retrieval tool (and with a community-search instance), which read full text from it.
        self.raw_content_cache: dict[str, str] = raw_content_cache if raw_content_cache is not None else {}
        self._max_results = max_results
        self._translator = translator
        # Reads the real date of forum and blog posts whose search result has none (see post_dates.py).
        self._date_recovery = date_recovery
        # When set, every search is restricted to the domains it returns for the place: this is how the
        # community search (forums, Reddit, regional communities) reuses all of this class's filtering.
        self._include_domains_for = include_domains_for

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
                extra = {"include_domains": self._include_domains_for(location)} if self._include_domains_for else {}
                response = self._client.search(
                    query=text,
                    max_results=self._max_results,
                    include_raw_content=True,
                    include_images=True,
                    **extra,
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

        candidates = _build_candidates(location, topic.topic_id, results, images, self.raw_content_cache, describe=True)
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
        for c in candidates:
            # A readable description is kept beside the text only where it is in the source's own language (a
            # translated item's description would still be the original), and only if a sentence qualified.
            if META_TRANSLATED_BY in c.metadata or not c.metadata.get("description"):
                c.metadata.pop("description", None)
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
        kept = [
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
        # Only what survived every filter is worth a page request for its date.
        if self._date_recovery is not None:
            self._date_recovery.enrich([c for c in kept if c.source_type in _DATED_SOURCE_TYPES])
        return kept


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
        date_recovery: PostDateRecovery | None = None,
    ) -> None:
        self.raw_content_cache: dict[str, str] = {}
        self._max_results = max_results
        self._translator = translator
        self._date_recovery = date_recovery

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

    def fetch(self, location: Location, *, refresh: bool = False) -> list[Evidence]:
        """Recent news and community conversation about a place's city, widening once to its region when the
        city has little. Items carry `feed_kind` ("news" or "community") and `feed_scope`.

        Served from a one-hour cache unless `refresh` is set (the user pressed the button). Concurrent
        identical requests share one search: the second waits for the first and reads its result."""
        cache_key = _feed_cache_key(location)
        with _FEED_CACHE_LOCK:
            gate = _FEED_INFLIGHT.setdefault(cache_key, threading.Lock())
        with gate:
            if not refresh:
                with _FEED_CACHE_LOCK:
                    cached = _FEED_CACHE.get(cache_key)
                if cached and time.monotonic() - cached[0] < _FEED_CACHE_TTL_SECONDS:
                    return cached[1]
            feed = self._build_feed(location, refresh=refresh)
            with _FEED_CACHE_LOCK:
                _FEED_CACHE[cache_key] = (time.monotonic(), feed)
            return feed

    def _build_feed(self, location: Location, *, refresh: bool) -> list[Evidence]:
        news: list[Evidence] = []
        community: list[Evidence] = []
        seen_urls: set[str] = set()
        queries_run = 0
        failures: list[str] = []
        for index, (scope, scoped) in enumerate(_feed_scopes(location)):
            if len(news) + len(community) >= _FEED_MIN_ITEMS:
                break
            label = _region_label(scoped)
            for kind, found in (("news", news), ("community", community)):
                if index > 0 and len(found) >= _FEED_MIN_PER_KIND:
                    continue
                candidates, ran, failed = self._search_scope(scoped, scope, kind, refresh=refresh)
                queries_run += ran
                failures.extend(failed)
                for item in candidates:
                    if item.source_url in seen_urls:
                        continue
                    seen_urls.add(item.source_url)
                    item.metadata["feed_kind"], item.metadata["feed_scope"] = kind, scope
                    item.location_scope = label
                    found.append(item)

        if queries_run and len(failures) == queries_run:
            raise ToolExecutionError("Tavily live-feed search failed for every query — " + "; ".join(failures))

        # Newest first. Only items with a real publication time can be dated, and they are ordered by it.
        news.sort(key=lambda e: e.published_at, reverse=True)
        community.sort(key=_newest_first_undated_last)
        if self._translator is not None:
            translate_evidence(news + community, self._translator, max_translations=_MAX_TRANSLATIONS_PER_SEARCH)

        return news + community

    def _search_scope(
        self, scoped: Location, scope: str, kind: str, *, refresh: bool = False
    ) -> tuple[list[Evidence], int, list[str]]:
        """One scope, one kind of content: one billed search, then the filters that keep it about this place.

        The result is cached per city (not per place), so the next place in the same city reuses it. Returns
        the items (fresh copies, safe to annotate), how many searches were actually sent (0 on a cache hit)
        and the failures."""
        label = _region_label(scoped)
        cache_key = (kind, scope, label.lower(), (scoped.country_code or "").lower())
        if not refresh:
            with _FEED_CACHE_LOCK:
                cached = _SCOPE_CACHE.get(cache_key)
            if cached and time.monotonic() - cached[0] < _FEED_CACHE_TTL_SECONDS:
                return [item.model_copy(deep=True) for item in cached[1]], 0, []

        if kind == "news":
            query = f"{label} {_NEWS_QUERY_GENERAL if scope == 'country' else _NEWS_QUERY_LOCAL}"
            extra: dict = {"topic": "news", "days": LIVE_FEED_WINDOW_DAYS}
        else:
            query = f"{label} {_COMMUNITY_FACET}"
            extra = {"include_domains": feed_domains(scoped.country_code)}

        try:
            # Basic depth is one credit; advanced is two, and nothing here needs it.
            response = self._client.search(
                query=query,
                max_results=self._max_results,
                search_depth="basic",
                include_raw_content=True,
                include_images=True,
                **extra,
            )
        except Exception as exc:  # noqa: BLE001 - the Tavily SDK's own exception types aren't guaranteed
            # A failed search is reported, not cached: the next load should try again.
            return [], 1, [f"'{query}': {exc}"]
        results = response.get("results", []) if isinstance(response, dict) else []
        images = response.get("images", []) if isinstance(response, dict) else []
        found = _build_candidates(scoped, "live_feed", results, images, self.raw_content_cache, describe=True)

        kept = []
        for item in found:
            if _is_non_activity_url(item.source_url):
                continue
            # News claims to be recent, so a result with no real publication time is dropped rather than
            # stamped with the moment it was fetched. Community posts are usually undated: they are kept and
            # shown as "date unknown". That is honest, unlike inventing a time.
            if kind == "news" and item.published_at is None:
                continue
            # No downstream verification here, so the location filter is not soft: a result with no
            # regional signal is dropped outright rather than shown with a caveat.
            if not _is_relevant_to_live_feed(item.source_title, item.text, scoped, f"{item.source_url} {item.publisher or ''}"):
                continue
            kept.append(item)
        for item in kept:
            # The filters above judged the full text; what the card shows is the readable description, or
            # nothing (title and source only) where no sentence qualified.
            item.text = item.metadata.pop("description", "")
        if kind == "community":
            # Every post has a date; the search API just does not say. Read it from the post itself where it
            # can be read (post_dates.py), and leave the rest undated rather than guess.
            if self._date_recovery is not None:
                self._date_recovery.enrich(kept)
            kept.sort(key=_newest_first_undated_last)
        with _FEED_CACHE_LOCK:
            _SCOPE_CACHE[cache_key] = (time.monotonic(), [item.model_copy(deep=True) for item in kept])
        return kept, 1, []


def _newest_first_undated_last(item: Evidence) -> tuple[bool, float]:
    return (item.published_at is None, -(item.published_at.timestamp() if item.published_at else 0.0))


def _feed_scopes(location: Location) -> list[tuple[str, Location]]:
    """The exact area first, then the region around it: "area", "region". Never the whole country, unless the
    country is all there is (a country-level place, or a bare name with no geography).

    The region scope drops the city, so the same query and relevance filter apply to the wider area. It is
    skipped when it would only repeat the area (Tokyo in Tokyo)."""
    scopes: list[tuple[str, Location]] = []
    if location.city:
        scopes.append(("area", location))
    if location.region and (location.region or "").lower() != (location.city or "").lower():
        scopes.append(("region", location.model_copy(update={"city": None})))
    if not scopes and location.country:
        scopes.append(("country", location.model_copy(update={"city": None, "region": None, "name": location.country})))
    return scopes or [("area", location)]


def _feed_cache_key(location: Location) -> tuple:
    named = "" if (location.city or location.region or location.country) else location.name.lower()
    return (named, (location.city or "").lower(), (location.region or "").lower(), (location.country or "").lower())


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
