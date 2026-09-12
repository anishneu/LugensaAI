from datetime import datetime, timezone

from app.models.evidence import Evidence, SourceType
from app.retrieval.keyword_retriever import KeywordEvidenceRetriever


def _evidence(evidence_id: str, title: str, text: str) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_url=f"https://example.org/{evidence_id}",
        source_title=title,
        source_type=SourceType.NEWS,
        retrieved_at=datetime.now(timezone.utc),
        location_scope="Cambridge, MA",
        text=text,
        topic="transportation",
    )


def test_higher_term_overlap_scores_higher():
    queries = ["Harvard Square public transportation MBTA commute"]
    strong_match = _evidence("e1", "MBTA Red Line at Harvard Square", "Frequent MBTA commute options near Harvard Square.")
    weak_match = _evidence("e2", "Local bakery review", "A bakery near the square with good pastries.")

    scored = KeywordEvidenceRetriever().score([weak_match, strong_match], queries)

    assert scored[0].evidence_id == "e1"
    assert scored[0].relevance_score > scored[1].relevance_score


def test_relevance_score_is_deterministic():
    queries = ["Harvard Square safety crime"]
    evidence = _evidence("e1", "Crime report", "Safety and crime statistics for Harvard Square.")

    first = KeywordEvidenceRetriever().score([evidence], queries)[0].relevance_score
    second = KeywordEvidenceRetriever().score([evidence], queries)[0].relevance_score

    assert first == second


def test_no_query_tokens_yields_zero_score():
    evidence = _evidence("e1", "Anything", "Any text at all.")

    scored = KeywordEvidenceRetriever().score([evidence], queries=[""])

    assert scored[0].relevance_score == 0.0
