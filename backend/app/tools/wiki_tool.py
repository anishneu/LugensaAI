"""Encyclopedic and travel-guide context from Wikipedia and Wikivoyage.

Free, no API key, and open content (CC BY-SA 4.0), which suits an open-source
project. It answers what the review and news sources tend not to: what is
actually near this spot (a station, a temple) and what a travel guide says about
the town for a visitor. For "is this a good place for a tourist?" that is
better evidence than any single review.

Two lookups, both anchored on the pin's coordinates so they cannot describe a
same-named place elsewhere:

* Wikipedia articles within a few kilometres (`list=geosearch`), introductions only.
* The Wikivoyage guide for the surrounding town, cut down to the passage that
  matches the question (`best_excerpt`), since a whole guide is far too long.

Wikimedia's API policy blocks requests whose User-Agent has no contact details,
so the agent identifies itself with the project's repository URL
(`WIKIMEDIA_CONTACT` overrides it). Every item is attributed to its source and
licence, and carries no publication date, because these pages have none that
means "when this was reported".
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx

from app.core.config import WIKIMEDIA_CONTACT
from app.models.evidence import Evidence, SourceType
from app.models.location import Location
from app.synthesis.excerpt import best_excerpt, query_terms
from app.tools.base import ToolExecutionError

_USER_AGENT = f"LugensaAI-LocationResearchAgent/0.1 ({WIKIMEDIA_CONTACT})"
_WIKIPEDIA_RADIUS_M = 3000
_WIKIVOYAGE_RADIUS_M = 12000
_MAX_WIKIPEDIA_ARTICLES = 3
_INTRO_CHARS = 900
_GUIDE_EXCERPT_CHARS = 1400
_LICENCE = "CC BY-SA 4.0"

_HEADING_RE = re.compile(r"^=+\s*(.*?)\s*=+\s*$", re.MULTILINE)
_WHITESPACE_RE = re.compile(r"[ \t]+")


def _tidy(text: str) -> str:
    """Turn `== Eat ==` headings into plain sentences' worth of text and collapse spaces."""
    text = _HEADING_RE.sub(lambda m: f"{m.group(1)}.", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


class WikiContextTool:
    """`transport` is exposed purely so tests can inject `httpx.MockTransport`."""

    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = 15.0) -> None:
        self._client = httpx.Client(transport=transport, timeout=timeout, headers={"User-Agent": _USER_AGENT})

    def _query(self, host: str, **params: object) -> dict:
        try:
            response = self._client.get(
                f"https://{host}/w/api.php", params={"action": "query", "format": "json", **params}
            )
            response.raise_for_status()
            return response.json().get("query", {})
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolExecutionError(f"{host} request failed: {exc}") from exc

    def _geosearch(self, host: str, location: Location, radius_m: int, limit: int) -> list[dict]:
        found = self._query(
            host,
            list="geosearch",
            gscoord=f"{location.latitude}|{location.longitude}",
            gsradius=radius_m,
            gslimit=limit,
        )
        return found.get("geosearch", [])

    def _extracts(self, host: str, titles: list[str], **params: object) -> list[dict]:
        pages = self._query(
            host, prop="extracts|info", inprop="url", explaintext=1, titles="|".join(titles), **params
        ).get("pages", {})
        return [page for page in pages.values() if page.get("extract")]

    def lookup(self, location: Location, question: str, topic_id: str) -> list[Evidence]:
        if location.latitude is None or location.longitude is None:
            return []
        retrieved_at = datetime.now(timezone.utc)
        scope = ", ".join(part for part in (location.city, location.region) if part) or location.name
        evidence: list[Evidence] = []

        nearby = self._geosearch("en.wikipedia.org", location, _WIKIPEDIA_RADIUS_M, _MAX_WIKIPEDIA_ARTICLES)
        if nearby:
            distances = {hit["title"]: round(hit.get("dist", 0)) for hit in nearby}
            for page in self._extracts(
                "en.wikipedia.org", list(distances), exintro=1, exchars=_INTRO_CHARS, exlimit="max"
            ):
                title = page["title"]
                evidence.append(
                    Evidence(
                        evidence_id=f"wikipedia:{page['pageid']}",
                        source_url=page.get("fullurl") or f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                        source_title=f"{title} (Wikipedia)",
                        publisher=f"Wikipedia ({_LICENCE})",
                        source_type=SourceType.REFERENCE,
                        retrieved_at=retrieved_at,
                        location_scope=scope,
                        text=f"{title} is about {distances.get(title, '?')} m from this location. "
                        + _tidy(page["extract"]),
                        topic=topic_id,
                        metadata={"provider": "wikimedia", "license": _LICENCE},
                    )
                )

        guide_hits = self._geosearch("en.wikivoyage.org", location, _WIKIVOYAGE_RADIUS_M, 1)
        guide_title = guide_hits[0]["title"] if guide_hits else location.city
        if guide_title:
            pages = self._extracts("en.wikivoyage.org", [guide_title], redirects=1)
            if pages:
                page = pages[0]
                excerpt = best_excerpt(_tidy(page["extract"]), query_terms(question), _GUIDE_EXCERPT_CHARS)
                evidence.append(
                    Evidence(
                        evidence_id=f"wikivoyage:{page['pageid']}",
                        source_url=page.get("fullurl") or f"https://en.wikivoyage.org/wiki/{guide_title}",
                        source_title=f"{page['title']} travel guide (Wikivoyage)",
                        publisher=f"Wikivoyage ({_LICENCE})",
                        source_type=SourceType.REFERENCE,
                        retrieved_at=retrieved_at,
                        location_scope=scope,
                        text=excerpt,
                        topic=topic_id,
                        metadata={"provider": "wikimedia", "license": _LICENCE},
                    )
                )
        return evidence
