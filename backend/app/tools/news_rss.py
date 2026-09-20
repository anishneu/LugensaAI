"""Recent news about a place from Google News' public RSS feed: free, no key, real publication dates.

Web search APIs are billed per search and return a ranked sample; this returns what news outlets published in a window, and
it accepts a quoted street name and a date limit (`when:30d`), which is what a feed about a specific street needs. Measured
live: "Massachusetts Avenue" Cambridge returned 14 items from the last 30 days from Cambridge Day, Patch, WBUR and NBC Boston;
"Cambridge" Massachusetts with police and crash terms returned 70.

It is an unofficial feed (Google documents it for feed readers, not as an API), so this is a polite client: a descriptive
user agent, a response size cap, a short timeout, every answer cached for 30 minutes, and any failure returns nothing rather
than an error. Items are headlines with a link and a publisher; there is no article text. The feed is untrusted input: a
response that declares a DOCTYPE or entities (the vector for XML entity attacks) is refused rather than parsed.

Each link goes through news.google.com, which sends the reader to the publisher.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from xml.etree import ElementTree

import httpx

_URL = "https://news.google.com/rss/search"
_USER_AGENT = "Mozilla/5.0 (compatible; LugensaAI/1.0; location research demo)"
_MAX_BYTES = 3_000_000
_MAX_ITEMS = 40
_CACHE_TTL_SECONDS = 30 * 60
_CACHE: dict[tuple[str, str], tuple[float, list["NewsItem"]]] = {}
_CACHE_LOCK = threading.Lock()

# Google's English edition for a country: (hl, gl, ceid). Countries not listed use English-language news about that country.
_EDITIONS: dict[str, tuple[str, str, str]] = {
    "US": ("en-US", "US", "US:en"),
    "GB": ("en-GB", "GB", "GB:en"),
    "AU": ("en-AU", "AU", "AU:en"),
    "CA": ("en-CA", "CA", "CA:en"),
    "IN": ("en-IN", "IN", "IN:en"),
    "IE": ("en-IE", "IE", "IE:en"),
    "NZ": ("en-NZ", "NZ", "NZ:en"),
    "SG": ("en-SG", "SG", "SG:en"),
    "ZA": ("en-ZA", "ZA", "ZA:en"),
}


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    publisher: str
    published_at: datetime


def _edition(country_code: str | None) -> tuple[str, str, str]:
    code = (country_code or "").upper()
    if code in _EDITIONS:
        return _EDITIONS[code]
    if len(code) == 2 and code.isalpha():
        return ("en", code, f"{code}:en")
    return _EDITIONS["US"]


def parse(content: bytes) -> list[NewsItem]:
    """The items of an RSS document, or nothing if it is not a safe, well-formed one."""
    if len(content) > _MAX_BYTES or b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        return []
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError:
        return []
    items: list[NewsItem] = []
    for node in root.findall("./channel/item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        source = node.find("source")
        publisher = (source.text or "").strip() if source is not None and source.text else ""
        try:
            published = parsedate_to_datetime(node.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue  # no readable date: not shown, and none is invented
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -len(publisher) - 3].rstrip()  # Google appends the outlet to the headline
        if title and link.startswith("http"):
            items.append(NewsItem(title=title, url=link, publisher=publisher, published_at=published))
    return items[:_MAX_ITEMS]


class GoogleNewsRss:
    """`transport` is exposed purely so tests can inject `httpx.MockTransport`."""

    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = 12.0) -> None:
        self._client = httpx.Client(transport=transport, timeout=timeout, headers={"User-Agent": _USER_AGENT}, follow_redirects=True)

    def search(self, query: str, days: int = 30, country_code: str | None = None) -> list[NewsItem]:
        """News matching `query` from the last `days` days, newest information first as Google ranks it. Empty on any failure."""
        text = query if "when:" in query else f"{query} when:{days}d"
        hl, gl, ceid = _edition(country_code)
        key = (text, ceid)
        with _CACHE_LOCK:
            cached = _CACHE.get(key)
        if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]
        try:
            response = self._client.get(f"{_URL}?q={quote_plus(text)}&hl={hl}&gl={gl}&ceid={ceid}")
        except httpx.HTTPError:
            return []
        if response.status_code != 200:
            return []
        items = parse(response.content)
        with _CACHE_LOCK:
            _CACHE[key] = (time.monotonic(), items)
        return items
