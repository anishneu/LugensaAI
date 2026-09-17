from datetime import datetime, timezone

import pytest

from app.models.evidence import Evidence, SourceType
from app.retrieval.hybrid_retriever import HybridEvidenceRetriever
from app.retrieval.keyword_retriever import KeywordEvidenceRetriever
from app.retrieval.semantic_retriever import SemanticEvidenceRetriever


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


def _fake_encode(texts: list[str]) -> list[list[float]]:
    vectors = []
    for text in texts:
        lowered = text.lower()
        transportation = 1.0 if any(w in lowered for w in ("commute", "transit", "campus", "getting to")) else 0.0
        vectors.append([transportation, 1.0 - transportation])
    return vectors


def _hybrid(keyword_weight: float = 0.5) -> HybridEvidenceRetriever:
    return HybridEvidenceRetriever(
        KeywordEvidenceRetriever(), SemanticEvidenceRetriever(encode_fn=_fake_encode), keyword_weight
    )


def test_finds_paraphrase_that_pure_keyword_retrieval_would_miss():
    queries = ["commute options"]
    paraphrase = _evidence("e1", "Campus access", "Getting to campus is easy without a car.")

    keyword_only = KeywordEvidenceRetriever().score([paraphrase], queries)[0].relevance_score
    hybrid = _hybrid().score([paraphrase], queries)[0].relevance_score

    assert keyword_only == 0.0  # no literal token overlap at all
    assert hybrid > keyword_only  # the semantic half picks it up


def test_rewards_evidence_that_matches_both_signals():
    queries = ["commute transit options"]
    both = _evidence("e1", "Transit commute", "Transit and commute info near campus.")
    neither = _evidence("e2", "Bakery", "A bakery with good pastries.")

    scored = _hybrid().score([both, neither], queries)

    assert scored[0].evidence_id == "e1"
    assert scored[0].relevance_score > scored[1].relevance_score


def test_keyword_weight_shifts_the_blend():
    queries = ["commute options"]
    paraphrase = _evidence("e1", "Campus access", "Getting to campus is easy without a car.")

    mostly_keyword = _hybrid(keyword_weight=0.9).score([paraphrase], queries)[0].relevance_score
    mostly_semantic = _hybrid(keyword_weight=0.1).score([paraphrase], queries)[0].relevance_score

    assert mostly_semantic > mostly_keyword


def test_rejects_invalid_weight():
    with pytest.raises(ValueError):
        HybridEvidenceRetriever(KeywordEvidenceRetriever(), SemanticEvidenceRetriever(encode_fn=_fake_encode), 1.5)


def test_empty_candidates_returns_empty():
    assert _hybrid().score([], ["query"]) == []
