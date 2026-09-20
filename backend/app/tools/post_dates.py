"""Real publication dates for forum and social posts whose search result carries none.

Every post has a date; the search API just does not pass it on (measured live: `published_date` is null for
every Reddit, PTT and Dcard result, and the scraped text of a Reddit thread has no date either). The date is
usually still readable from somewhere the source itself put it, and this module reads it from there, in order
of cost:

1. **The URL.** PTT names each article after its creation time (`M.1762748907.A.922.html`, seconds since the
   epoch), and many blogs and news sites put `/2026/09/17/` in the path. No request needed.
2. **Reddit** is the hard one. It blocks unauthenticated page and JSON requests, and its own Atom feed
   for a thread (`.../comments/<id>/.rss`) is throttled to roughly one request a minute for a client without
   an account (measured: 200, then 429 for the next 40 seconds, `x-ratelimit-remaining: 0`). So the primary
   source is Arctic Shift, a free public archive of Reddit that returns the post's `created_utc` for a whole
   batch of thread ids in one request (measured: 9 of 9 real ids in 0.9 s, and its date for one thread
   matched Reddit's own feed to the second). It is a third-party service, so a miss or an outage just leaves
   the post undated; the feed is tried only for the one or two posts the archive does not have (very new ones).
3. **The page's own metadata**: JSON-LD `datePublished` and the `article:published_time` family of meta tags.
   Never `dateModified`, and never a bare `<time>` tag, which on a forum is as likely to be a reply's time as
   the post's.

A date found this way is the source's own statement, not a guess, and `metadata["date_source"]` says where
it was read. If none applies (Dcard and the login-walled networks refuse a plain request), the post stays
undated and is shown as "date unknown": a missing date is honest, an invented one is not.

The page requests are free (no search credits) but not costless: at most `max_fetches` per call, a few seconds
each, run in parallel, only for posts that still lack a date, and only to public hosts. Set
`DISABLE_POST_DATE_FETCH=1` to use URL dates only.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlparse

from app.models.evidence import Evidence

DATE_SOURCE = "date_source"
SOURCE_URL = "url"
SOURCE_REDDIT_FEED = "reddit_feed"
SOURCE_REDDIT_ARCHIVE = "reddit_archive"
SOURCE_PAGE_METADATA = "page_metadata"

_USER_AGENT = "LugensaAI/1.0 (place research tool; reads a public post's publication date)"
_ARCHIVE_URL = "https://arctic-shift.photon-reddit.com/api/posts/ids?fields=id,created_utc&ids="
_MAX_ARCHIVE_IDS = 100
# Reddit's own feed is throttled to about one request a minute; it only backs up the archive for a couple of posts.
_MAX_REDDIT_FEED_FALLBACKS = 2
_TIMEOUT_SECONDS = 6
_MAX_BYTES = 300_000
_MAX_REDIRECTS = 3
_EARLIEST = datetime(2000, 1, 1, tzinfo=timezone.utc)

# Hosts that refuse a plain request (a login wall or a bot check). Trying them only wastes the time budget.
_UNFETCHABLE_HOSTS = ("dcard.tw", "facebook.com", "instagram.com", "tiktok.com", "x.com", "twitter.com", "linkedin.com")

_PTT_RE = re.compile(r"ptt\.cc/bbs/[^/]+/M\.(\d{9,10})\.A\.", re.IGNORECASE)
_PATH_DATE_RE = re.compile(r"/(20\d{2})[/-](0[1-9]|1[0-2])[/-](0[1-9]|[12]\d|3[01])(?=[/\-_.?#]|$)")
_REDDIT_RE = re.compile(r"reddit\.com/r/([^/]+)/comments/([a-z0-9]+)", re.IGNORECASE)
_ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.DOTALL)
_META_DATE_NAMES = {
    "article:published_time",
    "og:article:published_time",
    "datepublished",
    "pubdate",
    "publishdate",
    "publish_date",
    "date",
    "dc.date.issued",
    "dc.date",
    "dcterms.created",
    "parsely-pub-date",
    "sailthru.date",
}
_JSON_LD_KEYS = ("datePublished", "dateCreated", "uploadDate")


def parse_date(value: object) -> datetime | None:
    """A timezone-aware UTC datetime from an ISO or RFC-2822 string, or None. A date with no zone is read
    as UTC, and one before 2000 or more than a day in the future is rejected as a parse accident."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"  # Python before 3.11 cannot read a bare "Z"
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    return parsed if _EARLIEST <= parsed <= datetime.now(timezone.utc) + timedelta(days=1) else None


def date_from_url(url: str) -> datetime | None:
    """The date a URL states about itself: a PTT article's creation time, or a `/YYYY/MM/DD/` path."""
    ptt = _PTT_RE.search(url)
    if ptt:
        try:
            return parse_date(datetime.fromtimestamp(int(ptt.group(1)), tz=timezone.utc).isoformat())
        except (OverflowError, OSError, ValueError):
            return None
    path = _PATH_DATE_RE.search(urlparse(url).path)
    if path:
        return parse_date(f"{path.group(1)}-{path.group(2)}-{path.group(3)}")
    return None


def reddit_feed_url(url: str) -> str | None:
    """The Atom feed of a Reddit thread, or None for a URL that is not one."""
    match = _REDDIT_RE.search(url)
    return f"https://www.reddit.com/r/{match.group(1)}/comments/{match.group(2)}/_/.rss" if match else None


def reddit_post_id(url: str) -> str | None:
    match = _REDDIT_RE.search(url)
    return match.group(2).lower() if match else None


def dates_from_archive(response: str) -> dict[str, datetime]:
    """post id -> creation time, from an Arctic Shift `posts/ids` response. Anything malformed is skipped."""
    try:
        rows = json.loads(response).get("data", [])
    except (ValueError, AttributeError):
        return {}
    found: dict[str, datetime] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        created = row.get("created_utc")
        if isinstance(created, (int, float)) and not isinstance(created, bool):
            try:
                when = parse_date(datetime.fromtimestamp(created, tz=timezone.utc).isoformat())
            except (OverflowError, OSError, ValueError):
                continue
            if when:
                found[row["id"].lower()] = when
    return found


def date_from_reddit_feed(feed: str, post_id: str) -> datetime | None:
    """The post's own entry in a thread's Atom feed. The feed's top-level `<updated>` is the moment it was
    generated and the comments are entries too, so only the entry whose id is the post's counts."""
    for entry in _ENTRY_RE.findall(feed):
        if f"<id>t3_{post_id}</id>" in entry:
            stamp = re.search(r"<(?:published|updated)>([^<]+)</(?:published|updated)>", entry)
            return parse_date(stamp.group(1)) if stamp else None
    return None


class _MetadataParser(HTMLParser):
    """Collects the date-bearing meta tags and JSON-LD blocks of a page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta_dates: list[str] = []
        self.json_ld: list[str] = []
        self._in_json_ld = False
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: (value or "") for name, value in attrs}
        if tag == "meta":
            name = (values.get("property") or values.get("name") or values.get("itemprop") or "").lower()
            if name in _META_DATE_NAMES and values.get("content"):
                self.meta_dates.append(values["content"])
        elif tag == "time" and values.get("itemprop", "").lower() == "datepublished" and values.get("datetime"):
            self.meta_dates.append(values["datetime"])  # microdata: the post's own date, unlike a bare <time>
        elif tag == "script" and values.get("type", "").lower() == "application/ld+json":
            self._in_json_ld, self._buffer = True, []

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._buffer))
            self._in_json_ld = False


def _json_ld_date(node: object) -> str | None:
    if isinstance(node, dict):
        for key in _JSON_LD_KEYS:
            if isinstance(node.get(key), str):
                return node[key]
        for child in node.values():
            found = _json_ld_date(child)
            if found:
                return found
    elif isinstance(node, list):
        for child in node:
            found = _json_ld_date(child)
            if found:
                return found
    return None


def date_from_html(html: str) -> datetime | None:
    """The page's declared publication date: JSON-LD first (it names the entity it describes), then meta tags."""
    parser = _MetadataParser()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 - malformed markup must never break a search
        pass
    for block in parser.json_ld:
        try:
            found = parse_date(_json_ld_date(json.loads(block)))
        except ValueError:
            continue
        if found:
            return found
    for value in parser.meta_dates:
        found = parse_date(value)
        if found:
            return found
    return None


def fetching_enabled() -> bool:
    return os.environ.get("DISABLE_POST_DATE_FETCH", "").strip().lower() not in {"1", "true", "yes"}


def _is_public_host(host: str) -> bool:
    """Refuse to fetch anything that resolves to a private, loopback or link-local address. The URLs come
    from a search API, not from the user, but a page must never be a way into the local network."""
    if not host:
        return False
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError:
        return False
    return bool(addresses) and all(ipaddress.ip_address(a).is_global for a in addresses)


class _PublicOnlyRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = _MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        parsed = urlparse(newurl)
        if parsed.scheme not in ("http", "https") or not _is_public_host(parsed.hostname or ""):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_text(url: str) -> str | None:
    """A page's text (at most 300 KB), or None if it cannot be had for any reason."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not _is_public_host(parsed.hostname or ""):
        return None
    request = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/atom+xml"}
    )
    try:
        with urllib.request.build_opener(_PublicOnlyRedirects).open(request, timeout=_TIMEOUT_SECONDS) as response:
            return response.read(_MAX_BYTES).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None


class PostDateRecovery:
    """Fills in `published_at` on undated evidence from the URL, Reddit's feed or the page's metadata."""

    def __init__(
        self,
        fetch: Callable[[str], str | None] | None = None,
        *,
        max_fetches: int = 8,
        workers: int = 4,
    ) -> None:
        self._fetch = fetch if fetch is not None else (fetch_text if fetching_enabled() else None)
        self._max_fetches = max_fetches
        self._workers = workers

    def enrich(self, items: list[Evidence]) -> None:
        """Set `published_at` (and `metadata["date_source"]`) on each undated item where a real date can be
        read. Items that already have a date are never touched."""
        undated = [item for item in items if item.published_at is None]
        for item in undated:
            found = date_from_url(item.source_url)
            if found:
                self._set(item, found, SOURCE_URL)

        if self._fetch is None:
            return
        pending = [item for item in undated if item.published_at is None and not _is_unfetchable(item.source_url)]
        reddit = [item for item in pending if reddit_post_id(item.source_url)]
        others = [item for item in pending if not reddit_post_id(item.source_url)][: self._max_fetches]

        if reddit:
            self._date_reddit(reddit)
        if others:
            with ThreadPoolExecutor(max_workers=self._workers) as pool:
                for item, outcome in zip(others, pool.map(self._recover_from_page, others)):
                    if outcome:
                        self._set(item, *outcome)

    def _date_reddit(self, items: list[Evidence]) -> None:
        """One request for every thread's date, then Reddit's own feed for the one or two the archive lacks."""
        assert self._fetch is not None
        ids = list(dict.fromkeys(reddit_post_id(i.source_url) for i in items))[:_MAX_ARCHIVE_IDS]
        try:
            body = self._fetch(_ARCHIVE_URL + ",".join(i for i in ids if i))
            known = dates_from_archive(body) if body else {}
        except Exception:  # noqa: BLE001 - an archive outage leaves the posts undated, nothing more
            known = {}
        leftovers = []
        for item in items:
            when = known.get(reddit_post_id(item.source_url) or "")
            if when:
                self._set(item, when, SOURCE_REDDIT_ARCHIVE)
            else:
                leftovers.append(item)
        for item in leftovers[:_MAX_REDDIT_FEED_FALLBACKS]:
            outcome = self._recover_from_page(item)
            if outcome:
                self._set(item, *outcome)

    def _recover_from_page(self, item: Evidence) -> tuple[datetime, str] | None:
        assert self._fetch is not None
        try:
            feed_url = reddit_feed_url(item.source_url)
            if feed_url:
                body = self._fetch(feed_url)
                found = date_from_reddit_feed(body, reddit_post_id(item.source_url) or "") if body else None
                return (found, SOURCE_REDDIT_FEED) if found else None
            body = self._fetch(item.source_url)
            found = date_from_html(body) if body else None
            return (found, SOURCE_PAGE_METADATA) if found else None
        except Exception:  # noqa: BLE001 - one unreadable page must not cost the others their dates
            return None

    @staticmethod
    def _set(item: Evidence, when: datetime, source: str) -> None:
        item.published_at = when
        item.metadata[DATE_SOURCE] = source


def _is_unfetchable(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return any(host == blocked or host.endswith("." + blocked) for blocked in _UNFETCHABLE_HOSTS)
