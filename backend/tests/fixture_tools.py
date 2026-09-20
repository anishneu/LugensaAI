"""Test-only stand-ins backed by invented fixture documents (see tests/fixtures).

None of this is imported by `app/`. The product never serves fixture evidence, claims or places.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from app.models.claim import Claim
from app.models.evidence import Evidence, SourceType
from app.models.location import Location
from app.models.plan import ResearchPlan, ResearchTopic
from app.synthesis.claim_extractor import ClaimExtractor, ExtractionResult
from app.tools.base import LocationNotFoundError, LocationResolverTool, PageRetrievalTool, WebSearchTool
from tests.fixture_loader import FIXTURES_ROOT, iter_all_documents, load_locations, load_topic_documents


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower()).strip(",")


class FixtureLocationResolver(LocationResolverTool):
    """Resolves a raw location string against `fixtures/locations.json`.

    Stands in for a real geocoding API in Milestone 1. Matching is a simple
    alias lookup, not fuzzy geocoding.
    """

    def __init__(self, fixtures_root: Path = FIXTURES_ROOT) -> None:
        self._entries = load_locations(fixtures_root)

    def resolve(self, raw_query: str) -> Location:
        normalized = _normalize(raw_query)
        for entry in self._entries:
            aliases = [_normalize(a) for a in entry["aliases"]]
            if normalized in aliases:
                return self._to_location(entry, raw_query)
        for entry in self._entries:
            aliases = [_normalize(a) for a in entry["aliases"]]
            if any(normalized in alias or alias in normalized for alias in aliases):
                return self._to_location(entry, raw_query)
        raise LocationNotFoundError(f"Could not resolve location: {raw_query!r}")

    @staticmethod
    def _to_location(entry: dict, raw_query: str) -> Location:
        return Location(
            name=entry["name"],
            city=entry.get("city"),
            region=entry.get("region"),
            country=entry.get("country"),
            slug=entry["slug"],
            latitude=entry.get("latitude"),
            longitude=entry.get("longitude"),
            raw_query=raw_query,
        )


class FixtureWebSearchTool(WebSearchTool):
    """Returns candidate evidence for a topic from local fixture documents.

    A real implementation would issue `topic.search_queries` against a
    search API; this one ignores the query strings (they are still
    generated and logged for parity with the real interface) and returns
    curated fixture documents for the (location, topic) pair instead.
    """

    def __init__(self, fixtures_root: Path = FIXTURES_ROOT) -> None:
        self._fixtures_root = fixtures_root

    def search(self, location: Location, topic: ResearchTopic) -> list[Evidence]:
        documents = load_topic_documents(location.slug, topic.topic_id, self._fixtures_root)
        evidence: list[Evidence] = []
        for index, doc in enumerate(documents):
            published_at = datetime.fromisoformat(doc["published_at"]) if doc.get("published_at") else None
            evidence.append(
                Evidence(
                    evidence_id=f"{location.slug}:{topic.topic_id}:{index}",
                    source_url=doc["url"],
                    source_title=doc["title"],
                    publisher=doc.get("publisher"),
                    source_type=SourceType(doc["source_type"]),
                    retrieved_at=datetime.now(timezone.utc),
                    published_at=published_at,
                    location_scope=doc.get("location_scope", f"{location.city}, {location.region}"),
                    text=doc["snippet"],
                    topic=topic.topic_id,
                    metadata={"claim_text": doc["claim_text"]},
                )
            )
        return evidence


class FixturePageRetrievalTool(PageRetrievalTool):
    """Looks up the full extracted text for a URL from the same fixtures.

    Models the second step of a real search-then-fetch pipeline: the search
    tool returns a short snippet, and this tool fetches the fuller passage.
    """

    def __init__(self, fixtures_root: Path = FIXTURES_ROOT) -> None:
        self._index: dict[str, str] = {}
        for _slug, _topic_id, document in iter_all_documents(fixtures_root):
            self._index[document["url"]] = document["full_text"]

    def retrieve_full_text(self, source_url: str) -> str | None:
        return self._index.get(source_url)


class FixtureClaimExtractor(ClaimExtractor):
    """Groups fixture evidence by the pre-written `claim_text` each document carries.

    Only meaningful for fixture documents, which were written to support a specific claim. It cannot
    read a real page, which is why the product has no such extractor.
    """

    def extract(self, evidence: list[Evidence], plan: ResearchPlan) -> ExtractionResult:
        groups: dict[tuple[str, str], list[Evidence]] = {}
        for item in evidence:
            claim_text = item.metadata.get("claim_text")
            if not claim_text:
                continue
            groups.setdefault((item.topic, claim_text), []).append(item)

        claims = [
            Claim(
                claim_id=f"claim-{index:03d}",
                text=claim_text,
                claim_type=topic_id,
                supporting_evidence_ids=[item.evidence_id for item in items],
            )
            for index, ((topic_id, claim_text), items) in enumerate(groups.items())
        ]
        return ExtractionResult(claims=claims)


def fixture_agent(**kwargs):
    """The default agent, wired to the fixture places, sources and claims instead of live services."""
    from app.agents.factory import build_default_agent

    agent = build_default_agent(**kwargs)
    agent.location_resolver = FixtureLocationResolver()
    agent.web_search_tool = FixtureWebSearchTool()
    agent.page_retrieval_tool = FixturePageRetrievalTool()
    if not hasattr(agent.claim_extractor, "_llm"):
        agent.claim_extractor = FixtureClaimExtractor()
    return agent
