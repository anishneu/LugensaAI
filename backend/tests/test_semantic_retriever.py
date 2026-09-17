from datetime import datetime, timezone

from app.models.evidence import Evidence, SourceType
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
    """A crude two-dimensional concept embedding: [transportation-ish, unrelated-ish].

    Lets us test that semantic scoring can match a paraphrase with zero
    literal token overlap — the exact gap docs/research-workflow.md
    describes for the keyword retriever — without loading a real model.
    """
    vectors = []
    for text in texts:
        lowered = text.lower()
        transportation = 1.0 if any(w in lowered for w in ("commute", "transit", "campus", "getting to")) else 0.0
        vectors.append([transportation, 1.0 - transportation])
    return vectors


def test_matches_paraphrase_with_no_literal_token_overlap():
    queries = ["commute options"]
    paraphrase = _evidence("e1", "Campus access", "Getting to campus is easy without a car.")
    unrelated = _evidence("e2", "Local bakery", "A bakery with good pastries.")

    scored = SemanticEvidenceRetriever(encode_fn=_fake_encode).score([unrelated, paraphrase], queries)

    assert scored[0].evidence_id == "e1"
    assert scored[0].relevance_score > scored[1].relevance_score


def test_score_is_deterministic_for_a_fixed_encoder():
    queries = ["commute options"]
    evidence = _evidence("e1", "Campus access", "Getting to campus is easy.")

    first = SemanticEvidenceRetriever(encode_fn=_fake_encode).score([evidence], queries)[0].relevance_score
    second = SemanticEvidenceRetriever(encode_fn=_fake_encode).score([evidence], queries)[0].relevance_score

    assert first == second


def test_empty_candidates_returns_empty_without_encoding():
    calls: list[list[str]] = []

    def tracking_encode(texts: list[str]) -> list[list[float]]:
        calls.append(texts)
        return _fake_encode(texts)

    result = SemanticEvidenceRetriever(encode_fn=tracking_encode).score([], ["query"])

    assert result == []
    assert calls == []
