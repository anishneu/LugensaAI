"""The evaluation's frozen evidence: the real pipeline must read only what it is given and reach for nothing else."""

from datetime import datetime, timezone

from app.models.evidence import Evidence, SourceType
from app.models.location import Location
from evaluation.frozen_corpus import FrozenPages, FrozenSearch, build_frozen_agent

LOCATION = Location(
    name="Harvard Square", city="Cambridge", region="Massachusetts", country="United States", slug="hs",
    latitude=42.3736, longitude=-71.119, raw_query="Harvard Square, Cambridge, MA",
)


def _item(n: int, text: str) -> Evidence:
    return Evidence(
        evidence_id=f"e{n}", source_url=f"https://example.org/{n}", source_title=f"Source {n}", source_type=SourceType.OTHER,
        retrieved_at=datetime.now(timezone.utc), location_scope="Cambridge", text=text, topic="general",
    )


CORPUS = [
    _item(1, "The Red Line subway stops at Harvard Square, so getting around Cambridge without a car is easy and safe."),
    _item(2, "Late night bars and live music venues around Harvard Square stay open until two in the morning on weekends."),
]


def test_every_topic_search_returns_the_whole_frozen_set_tagged_with_that_topic():
    from app.planning.planner import KeywordResearchPlanner

    topics = KeywordResearchPlanner().plan(LOCATION, "What's the nightlife like?").topics
    found = FrozenSearch(CORPUS).search(LOCATION, topics[0])

    assert len(found) == 2 and all(e.topic == topics[0].topic_id for e in found)
    assert len({e.evidence_id for e in found}) == 2  # ids stay unique per topic
    assert FrozenPages().retrieve_full_text("https://example.org/1") is None


def test_the_agent_built_on_a_frozen_set_answers_from_it_and_has_nothing_that_reaches_the_network():
    agent = build_frozen_agent(CORPUS, use_llm=False)

    for part in ("community_search_tool", "regional_search_tool", "reddit_archive_tool", "wiki_tool", "place_profile_tool", "reflector"):
        assert getattr(agent, part) is None

    response = agent.run(LOCATION, "What's the nightlife like around here?")

    assert response.evidence and {e.source_url for e in response.evidence} <= {e.source_url for e in CORPUS}
