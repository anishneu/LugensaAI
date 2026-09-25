"""A fixed set of real sources per case, collected once from the free sources, so every system in the comparison reads exactly
the same evidence and a run spends no search credit.

Collected from what costs nothing: Wikipedia and Wikivoyage around the pin, the free Reddit archive, and Google News' public RSS
(headlines, English edition). The corpora are third parties' text, so they are written to `evaluation/corpora/` which is
gitignored: what is committed is the code and the measured results, and anyone can collect their own (the sources change over
time, so results will differ a little; the results file records when each corpus was collected and how big it was).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.agents.factory import build_default_agent
from app.models.evidence import Evidence, SourceType
from app.models.location import Location
from app.models.plan import ResearchTopic
from app.tools.base import PageRetrievalTool, WebSearchTool
from evaluation.quality_cases import QualityCase

CORPUS_DIR = Path(__file__).resolve().parent / "corpora"
MAX_ITEMS = 40


def corpus_path(case: QualityCase) -> Path:
    return CORPUS_DIR / f"{case.case_id}.json"


def collect(case: QualityCase) -> dict:
    """Resolve the place and gather its free evidence. Slow (the Reddit archive is rate-limited) and networked."""
    from app.planning.planner import KeywordResearchPlanner
    from app.tools.news_rss import GoogleNewsRss
    from app.tools.nominatim_tool import NominatimLocationResolverTool
    from app.tools.reddit_archive import RedditArchiveTool
    from app.tools.wiki_tool import WikiContextTool

    from app.tools.community_sources import base_name
    from app.tools.wikidata_names import WikidataNameVariants

    location = NominatimLocationResolverTool().resolve(case.place)
    if case.is_business:
        location = location.model_copy(update={"is_business": True})
    # The agent asks Wikidata for a place's other English names before it searches (a Reddit thread may use a different
    # spelling than OpenStreetMap does), so the collection does too.
    try:
        others = [v for v in WikidataNameVariants().variants(base_name(location.name), location.latitude, location.longitude)
                  if base_name(v).lower() != base_name(location.name).lower()]
        if others:
            location = location.model_copy(update={"name_variants": others})
            print(f"  other names: {', '.join(others[:4])}")
    except Exception as exc:
        print(f"  wikidata names failed: {type(exc).__name__}")

    found: list[tuple[str, Evidence]] = []
    try:
        found += [("wikimedia", e) for e in WikiContextTool().lookup(location, case.question, "general")]
    except Exception as exc:  # a source being down is a fact about that source, not a reason to stop
        print(f"  wikimedia failed: {type(exc).__name__}")
    try:
        topic = KeywordResearchPlanner().plan(location, case.question).topics[0]
        found += [("reddit", e) for e in RedditArchiveTool().search(location, topic)]
    except Exception as exc:
        print(f"  reddit archive failed: {type(exc).__name__}")
    try:
        query = f'"{location.name}" {location.city or ""}'.strip()
        now = datetime.now(timezone.utc)
        for item in GoogleNewsRss().search(query, days=365):
            found.append((
                "news",
                Evidence(
                    evidence_id="news-" + hashlib.md5(item.url.encode()).hexdigest()[:10],
                    source_url=item.url,
                    source_title=item.title,
                    publisher=item.publisher,
                    source_type=SourceType.NEWS,
                    retrieved_at=now,
                    published_at=item.published_at,
                    location_scope=location.city or location.name,
                    text=item.title,  # the feed carries headlines only
                    topic="general",
                ),
            ))
    except Exception as exc:
        print(f"  news rss failed: {type(exc).__name__}")

    seen: set[str] = set()
    evidence: list[Evidence] = []
    counts: dict[str, int] = {}
    for source, item in found:
        if item.source_url in seen or len(evidence) >= MAX_ITEMS:
            continue
        seen.add(item.source_url)
        evidence.append(item)
        counts[source] = counts.get(source, 0) + 1

    payload = {
        "case_id": case.case_id,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "location": location.model_dump(mode="json"),
        "counts": counts,
        "evidence": [e.model_dump(mode="json") for e in evidence],
    }
    CORPUS_DIR.mkdir(exist_ok=True)
    corpus_path(case).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return payload


def load(case: QualityCase) -> tuple[Location, list[Evidence], dict]:
    payload = json.loads(corpus_path(case).read_text(encoding="utf-8"))
    return (
        Location.model_validate(payload["location"]),
        [Evidence.model_validate(e) for e in payload["evidence"]],
        {"collected_at": payload["collected_at"], "counts": payload["counts"]},
    )


class FrozenSearch(WebSearchTool):
    """A 'search engine' over a fixed set of evidence: every topic's search returns all of it, and the pipeline's own
    relevance scoring decides what each topic keeps, exactly as it would for a live search's results."""

    def __init__(self, evidence: list[Evidence]) -> None:
        self._evidence = evidence

    def search(self, location: Location, topic: ResearchTopic) -> list[Evidence]:
        return [
            e.model_copy(update={"topic": topic.topic_id, "evidence_id": f"{e.evidence_id}:{topic.topic_id}"})
            for e in self._evidence
        ]


class FrozenPages(PageRetrievalTool):
    """The frozen evidence already holds its text; there is nothing more to fetch."""

    def retrieve_full_text(self, source_url: str) -> str | None:
        return None


# Everything in the agent that would reach the network is switched off: the frozen corpus is all it may read.
_NETWORK_PARTS = (
    "community_search_tool", "regional_search_tool", "reddit_archive_tool", "name_variants_tool", "wiki_tool",
    "place_profile_tool", "reflector", "locale_resolver", "local_query_writer",
)


def build_frozen_agent(evidence: list[Evidence], use_llm: bool = True):
    """The real pipeline (planner, retrieval, claim extraction, verification, synthesis) reading only `evidence`.

    Left out on purpose: the follow-up research loop (there is nothing new to fetch from a frozen set) and the sources that
    would reach the network. So this measures reading and answering, not searching."""
    agent = build_default_agent(
        use_llm=use_llm, use_live_search=False, use_live_geocoding=False, db_path=Path(tempfile.mkdtemp()) / "evidence.db"
    )
    agent.web_search_tool = FrozenSearch(evidence)
    agent.page_retrieval_tool = FrozenPages()
    for part in _NETWORK_PARTS:
        setattr(agent, part, None)
    return agent
