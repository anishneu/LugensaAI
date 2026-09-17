"""Live web search + page retrieval via the Tavily API (Milestone 3).

Requires `TAVILY_API_KEY` (see `app/core/config.py`); nothing here is
imported or constructed unless that key is set (`app/agents/factory.py`
gates it the same way it gates the Milestone 2 LLM components).

Tavily's `include_raw_content=True` returns full extracted page text in the
same search call, so `TavilyPageRetrievalTool` doesn't make a second network
request per result — it just reads from a cache populated by the search
call for the same run, sharing the same conceptual two-step
search-then-retrieve interface as the fixture tools without paying for a
second real HTTP request per source.

Real web results don't arrive pre-labeled with a clean `source_type` the
way curated fixtures do. `_classify_source_type()` is a coarse, honest
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

Important limitation this milestone does not fix: `FixtureClaimExtractor`
cannot produce claims from real evidence text (it only knows how to read
fixture-annotated `claim_text` metadata). Live search evidence needs
`LLMClaimExtractor` (Milestone 2) to actually turn into claims — see
`backend/README.md`.
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

_GOV_TLDS = (".gov",)
_EDU_TLDS = (".edu",)
_FORUM_DOMAINS = ("reddit.com", "quora.com", "nextdoor.com")
_REVIEW_DOMAINS = ("yelp.com", "tripadvisor.com", "zillow.com", "apartments.com", "google.com/maps")
_BLOG_DOMAINS = ("medium.com", "substack.com", "blogspot.com")

_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HEADING_RE = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_TIMESTAMP_LINE_RE = re.compile(r"^\s*\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s.*$", re.MULTILINE)
_APP_STORE_LINE_RE = re.compile(r"^.*(app-store|play\.google\.com|Get our ?App).*$", re.MULTILINE | re.IGNORECASE)
_NAV_MENU_LINE_RE = re.compile(r"^(?:[^\n|]*\|){3,}[^\n]*$", re.MULTILINE)
_BULLET_NAV_BLOCK_RE = re.compile(r"(?:^[ \t]*[*•]\s.{0,60}$\n?){3,}", re.MULTILINE)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")

# Exact-match, case-insensitive: known UI chrome from specific platforms
# (Facebook, Nextdoor, Zillow, ...) observed in real scraped results. A
# denylist of known junk lines, rather than a generic "short line" filter —
# a generic filter would also gut legitimate short-line content like a
# crime-statistics table (numbers and place names are short lines too, and
# those are exactly the kind of safety data this project wants surfaced).
_KNOWN_UI_JUNK_LINES = {
    "log in",
    "forgot account?",
    "video home",
    "live reels",
    "explore more",
    "explore video",
    "sign up",
    "create new account",
    "see more",
    "where is this data from?",
    "don't miss out!",
    "see what verified neighbors are saying",
    "loadingloading...",
    "total monthly price",
}

_MIN_USABLE_SNIPPET_LENGTH = 40
_MAX_DISPLAY_LENGTH = 1200
_MAX_FULL_TEXT_LENGTH = 3000


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
    cleaned = _HEADING_RE.sub("", cleaned)
    cleaned = _TIMESTAMP_LINE_RE.sub("", cleaned)
    cleaned = _APP_STORE_LINE_RE.sub("", cleaned)
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
    return any(needle in haystack for needle in needles if needle)


def _classify_source_type(url: str) -> SourceType:
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    if domain.endswith(_GOV_TLDS):
        return SourceType.LOCAL_GOVERNMENT
    if domain.endswith(_EDU_TLDS):
        return SourceType.ACADEMIC
    if any(d in domain for d in _FORUM_DOMAINS):
        return SourceType.COMMUNITY_FORUM
    if any(d in url.lower() for d in _REVIEW_DOMAINS):
        return SourceType.REVIEW_AGGREGATOR
    if any(d in domain for d in _BLOG_DOMAINS):
        return SourceType.BLOG
    return SourceType.OTHER


def _parse_published_date(value: object) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def _evidence_id(topic_id: str, url: str) -> str:
    return f"tavily:{topic_id}:{hashlib.sha1(url.encode('utf-8')).hexdigest()[:12]}"


def _extract_image_url(raw_image: object) -> str | None:
    if isinstance(raw_image, str):
        return raw_image
    if isinstance(raw_image, dict):
        url = raw_image.get("url")
        return url if isinstance(url, str) else None
    return None


class TavilyWebSearchTool(WebSearchTool):
    def __init__(self, api_key: str | None = None, max_results: int = 4, client: object | None = None) -> None:
        self.raw_content_cache: dict[str, str] = {}
        self._max_results = max_results

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

    def search(self, location: Location, topic: ResearchTopic) -> list[Evidence]:
        location_label = f"{location.name}, {location.city}, {location.region}".strip(", ")
        query = topic.search_queries[0] if topic.search_queries else f"{location_label} {topic.topic_id}"

        try:
            response = self._client.search(
                query=query,
                max_results=self._max_results,
                include_raw_content=True,
                include_images=True,
            )
        except Exception as exc:  # noqa: BLE001 - the Tavily SDK's own exception types aren't guaranteed
            raise ToolExecutionError(f"Tavily search failed for query '{query}': {exc}") from exc

        results = response.get("results", []) if isinstance(response, dict) else []
        images = response.get("images", []) if isinstance(response, dict) else []

        candidates: list[Evidence] = []
        for index, item in enumerate(results):
            url = item.get("url")
            if not url:
                continue
            raw_content = _truncate_for_display(_clean_text(item.get("raw_content") or ""), _MAX_FULL_TEXT_LENGTH)
            snippet = _truncate_for_display(_clean_text(item.get("content") or raw_content[:500]))
            title = item.get("title") or url

            if len(snippet) < _MIN_USABLE_SNIPPET_LENGTH:
                # Cleaning (stripping nav menus, timestamps, markdown) can leave
                # almost nothing behind for some sources (e.g. a video whose
                # "content" was mostly chapter markers) — not worth keeping.
                continue
            if not _is_relevant_to_location(f"{title} {snippet}", location):
                continue

            self.raw_content_cache[url] = raw_content or snippet

            candidates.append(
                Evidence(
                    evidence_id=_evidence_id(topic.topic_id, url),
                    source_url=url,
                    source_title=title,
                    publisher=urlparse(url).netloc.removeprefix("www.") or None,
                    source_type=_classify_source_type(url),
                    retrieved_at=datetime.now(timezone.utc),
                    published_at=_parse_published_date(item.get("published_date")),
                    location_scope=f"{location.city}, {location.region}",
                    text=snippet,
                    topic=topic.topic_id,
                    metadata={"provider": "tavily", "is_fixture": "false"},
                    image_url=_extract_image_url(images[index]) if index < len(images) else None,
                )
            )

        # Soft filter: an empty topic with an honest coverage-gap limitation
        # is better than quietly keeping off-topic results to avoid it, but
        # dropping every single candidate (e.g. the location name appears
        # only in the query, never in any real result) would be worse than
        # showing the unfiltered results with a lower relevance score.
        if candidates:
            return candidates

        return self._build_unfiltered(location, topic, results, images)

    def _build_unfiltered(
        self, location: Location, topic: ResearchTopic, results: list[dict], images: list
    ) -> list[Evidence]:
        evidence: list[Evidence] = []
        for index, item in enumerate(results):
            url = item.get("url")
            if not url:
                continue
            raw_content = _truncate_for_display(_clean_text(item.get("raw_content") or ""), _MAX_FULL_TEXT_LENGTH)
            snippet = _truncate_for_display(_clean_text(item.get("content") or raw_content[:500]))
            self.raw_content_cache[url] = raw_content or snippet
            evidence.append(
                Evidence(
                    evidence_id=_evidence_id(topic.topic_id, url),
                    source_url=url,
                    source_title=item.get("title") or url,
                    publisher=urlparse(url).netloc.removeprefix("www.") or None,
                    source_type=_classify_source_type(url),
                    retrieved_at=datetime.now(timezone.utc),
                    published_at=_parse_published_date(item.get("published_date")),
                    location_scope=f"{location.city}, {location.region}",
                    text=snippet,
                    topic=topic.topic_id,
                    metadata={"provider": "tavily", "is_fixture": "false", "location_match": "false"},
                    image_url=_extract_image_url(images[index]) if index < len(images) else None,
                )
            )
        return evidence


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
