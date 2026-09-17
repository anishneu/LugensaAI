from datetime import datetime, timezone

from app.core.config import AgentConfig
from app.models.claim import Claim, ClaimStatus
from app.models.evidence import Evidence, SourceType
from app.verification.verifier import EvidenceBasedClaimVerifier


def _evidence(evidence_id: str, relevance_score: float, recency_days: int | None = 10) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_url=f"https://example.org/{evidence_id}",
        source_title="Title",
        source_type=SourceType.NEWS,
        retrieved_at=datetime.now(timezone.utc),
        location_scope="Cambridge, MA",
        text="Some text.",
        topic="housing",
        relevance_score=relevance_score,
        recency_days=recency_days,
    )


def test_claim_with_relevant_evidence_is_supported():
    evidence = _evidence("e1", relevance_score=0.5)
    claim = Claim(claim_id="c1", text="Rent is high.", claim_type="housing", supporting_evidence_ids=["e1"])
    config = AgentConfig()

    [verified] = EvidenceBasedClaimVerifier().verify([claim], {"e1": evidence}, config)

    assert verified.status == ClaimStatus.SUPPORTED
    assert verified.limitations == []


def test_claim_with_no_supporting_evidence_ids_is_insufficient():
    claim = Claim(claim_id="c1", text="Rent is high.", claim_type="housing", supporting_evidence_ids=[])
    config = AgentConfig()

    [verified] = EvidenceBasedClaimVerifier().verify([claim], {}, config)

    assert verified.status == ClaimStatus.INSUFFICIENT_EVIDENCE
    assert verified.limitations


def test_claim_below_relevance_threshold_is_insufficient():
    evidence = _evidence("e1", relevance_score=0.05)
    claim = Claim(claim_id="c1", text="Rent is high.", claim_type="housing", supporting_evidence_ids=["e1"])
    config = AgentConfig(min_relevance_score=0.15)

    [verified] = EvidenceBasedClaimVerifier().verify([claim], {"e1": evidence}, config)

    assert verified.status == ClaimStatus.INSUFFICIENT_EVIDENCE


def test_stale_evidence_still_supports_but_adds_limitation():
    evidence = _evidence("e1", relevance_score=0.5, recency_days=1000)
    claim = Claim(claim_id="c1", text="Rent is high.", claim_type="housing", supporting_evidence_ids=["e1"])
    config = AgentConfig(stale_evidence_days=730)

    [verified] = EvidenceBasedClaimVerifier().verify([claim], {"e1": evidence}, config)

    assert verified.status == ClaimStatus.SUPPORTED
    assert any("older than" in limitation for limitation in verified.limitations)


def test_two_supported_claims_that_contradict_are_both_marked_contradicted():
    evidence_a = _evidence("e1", relevance_score=0.5)
    evidence_b = _evidence("e2", relevance_score=0.5)
    claim_a = Claim(
        claim_id="c1", text="The area is very safe at night.", claim_type="safety", supporting_evidence_ids=["e1"]
    )
    claim_b = Claim(
        claim_id="c2", text="Residents describe it as a dangerous area.", claim_type="safety",
        supporting_evidence_ids=["e2"],
    )
    config = AgentConfig()

    verified = EvidenceBasedClaimVerifier().verify(
        [claim_a, claim_b], {"e1": evidence_a, "e2": evidence_b}, config
    )

    assert {c.status for c in verified} == {ClaimStatus.CONTRADICTED}
    by_id = {c.claim_id: c for c in verified}
    assert by_id["c1"].contradicting_evidence_ids == ["e2"]
    assert by_id["c2"].contradicting_evidence_ids == ["e1"]
    assert any("contradict" in lim for lim in by_id["c1"].limitations)


def test_contradiction_check_ignores_different_topics():
    evidence_a = _evidence("e1", relevance_score=0.5)
    evidence_b = _evidence("e2", relevance_score=0.5)
    claim_a = Claim(
        claim_id="c1", text="The area is very safe at night.", claim_type="safety", supporting_evidence_ids=["e1"]
    )
    claim_b = Claim(
        claim_id="c2", text="It is a dangerous place to invest money.", claim_type="cost_of_living",
        supporting_evidence_ids=["e2"],
    )
    config = AgentConfig()

    verified = EvidenceBasedClaimVerifier().verify(
        [claim_a, claim_b], {"e1": evidence_a, "e2": evidence_b}, config
    )

    assert all(c.status == ClaimStatus.SUPPORTED for c in verified)


def test_contradiction_check_ignores_claims_without_sufficient_evidence():
    evidence_a = _evidence("e1", relevance_score=0.5)
    claim_a = Claim(
        claim_id="c1", text="The area is very safe at night.", claim_type="safety", supporting_evidence_ids=["e1"]
    )
    claim_b = Claim(
        claim_id="c2", text="It is a dangerous area.", claim_type="safety", supporting_evidence_ids=[]
    )
    config = AgentConfig()

    verified = EvidenceBasedClaimVerifier().verify([claim_a, claim_b], {"e1": evidence_a}, config)

    by_id = {c.claim_id: c for c in verified}
    assert by_id["c1"].status == ClaimStatus.SUPPORTED  # unsupported claim can't drag a supported one down
    assert by_id["c2"].status == ClaimStatus.INSUFFICIENT_EVIDENCE
