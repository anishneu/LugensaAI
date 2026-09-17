import json
from datetime import datetime, timezone

from app.models.evidence import Evidence, SourceType
from app.models.plan import ResearchPlan
from app.synthesis.claim_extractor import FixtureClaimExtractor
from app.synthesis.llm_claim_extractor import LLMClaimExtractor
from tests.llm_doubles import ScriptedLLMService


def _evidence(evidence_id: str, topic: str) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_url=f"https://example.org/{evidence_id}",
        source_title="Title",
        source_type=SourceType.NEWS,
        retrieved_at=datetime.now(timezone.utc),
        location_scope="Cambridge, MA",
        text="Some passage.",
        topic=topic,
    )


def _plan() -> ResearchPlan:
    return ResearchPlan(question="q", topics=[])


def test_extracts_claims_grounded_in_given_evidence():
    evidence = [_evidence("e1", "housing"), _evidence("e2", "housing")]
    response = json.dumps(
        {"claims": [{"topic_id": "housing", "text": "Rent is high.", "supporting_evidence_ids": ["e1", "e2"]}]}
    )
    extractor = LLMClaimExtractor(ScriptedLLMService([response]))

    result = extractor.extract(evidence, _plan())

    assert len(result.claims) == 1
    assert set(result.claims[0].supporting_evidence_ids) == {"e1", "e2"}
    assert result.notes == []


def test_drops_hallucinated_evidence_ids_but_keeps_claim_if_any_valid_remain():
    evidence = [_evidence("e1", "housing")]
    response = json.dumps(
        {"claims": [{"topic_id": "housing", "text": "Rent is high.", "supporting_evidence_ids": ["e1", "e999-fake"]}]}
    )
    extractor = LLMClaimExtractor(ScriptedLLMService([response]))

    result = extractor.extract(evidence, _plan())

    assert len(result.claims) == 1
    assert result.claims[0].supporting_evidence_ids == ["e1"]
    assert any("don't correspond to real evidence" in note for note in result.notes)


def test_drops_claim_with_no_valid_evidence_ids_and_falls_back():
    evidence = [_evidence("e1", "housing")]
    response = json.dumps(
        {"claims": [{"topic_id": "housing", "text": "Rent is high.", "supporting_evidence_ids": ["totally-fake"]}]}
    )
    extractor = LLMClaimExtractor(ScriptedLLMService([response]), fallback=FixtureClaimExtractor())

    result = extractor.extract(evidence, _plan())

    assert any("LLM-based claim extraction failed" in note for note in result.notes)


def test_falls_back_on_llm_error():
    evidence = [_evidence("e1", "housing")]
    extractor = LLMClaimExtractor(ScriptedLLMService(raise_error=True), fallback=FixtureClaimExtractor())

    result = extractor.extract(evidence, _plan())

    assert any("LLM-based claim extraction failed" in note for note in result.notes)


def test_no_evidence_returns_empty_without_calling_llm():
    llm = ScriptedLLMService()
    extractor = LLMClaimExtractor(llm)

    result = extractor.extract([], _plan())

    assert result.claims == []
    assert llm.calls == []
