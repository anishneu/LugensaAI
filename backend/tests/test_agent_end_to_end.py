import pytest

from app.agents.factory import build_default_agent
from app.core.config import AgentConfig
from app.models.claim import ClaimStatus
from app.models.trace import TraceStage
from app.tools.base import LocationNotFoundError


def test_harvard_square_college_student_full_pipeline():
    agent = build_default_agent()

    response = agent.run("Harvard Square, Cambridge, MA", "Would this be a good place for a college student?")

    assert response.location.name == "Harvard Square"
    assert {t.topic_id for t in response.topics} == {
        "housing",
        "transportation",
        "safety",
        "student_amenities",
        "cost_of_living",
    }

    # Every planned topic found real evidence — no coverage gaps for this fully-fixtured location.
    evidence_topics = {e.topic for e in response.evidence}
    assert evidence_topics == {t.topic_id for t in response.topics}
    assert len(response.evidence) == 10  # 2 fixture docs per topic x 5 topics

    # Every evidence item traces back to a real source with a passage.
    for evidence in response.evidence:
        assert evidence.source_url
        assert evidence.text
        assert evidence.relevance_score is not None
        assert evidence.quality_score is not None

    # Every claim is linked to evidence that actually exists, and status was assigned by the verifier.
    assert len(response.claims) == 6  # 1 claim per topic, except cost_of_living has 2 distinct claims
    for claim in response.claims:
        assert claim.supporting_evidence_ids
        assert claim.status in (ClaimStatus.SUPPORTED, ClaimStatus.INSUFFICIENT_EVIDENCE)
        for evidence_id in claim.supporting_evidence_ids:
            assert evidence_id in {e.evidence_id for e in response.evidence}

    supported_claims = [c for c in response.claims if c.status == ClaimStatus.SUPPORTED]
    assert len(supported_claims) == 6  # all evidence in the fixtures is relevant enough to support its claim

    # The one deliberately stale fixture source (2022) surfaces as a limitation, not a silent pass.
    assert any("older than" in limitation for limitation in response.limitations)
    # The honesty note about contradiction detection is always present.
    assert any("contradiction detection" in limitation.lower() for limitation in response.limitations)

    assert response.summary
    assert response.recommendation
    assert "generally supportive" in response.recommendation

    trace_stages = {step.stage for step in response.research_trace}
    assert TraceStage.LOCATION_RESOLUTION in trace_stages
    assert TraceStage.RESEARCH_PLANNING in trace_stages
    assert TraceStage.RETRIEVAL in trace_stages
    assert TraceStage.CLAIM_EXTRACTION in trace_stages
    assert TraceStage.CLAIM_VERIFICATION in trace_stages
    assert TraceStage.SYNTHESIS in trace_stages


def test_nightlife_question_only_researches_nightlife():
    agent = build_default_agent()

    response = agent.run("Harvard Square, Cambridge, MA", "What's the nightlife like around here?")

    assert {t.topic_id for t in response.topics} == {"nightlife"}
    assert {e.topic for e in response.evidence} == {"nightlife"}
    assert all(c.claim_type == "nightlife" for c in response.claims)


def test_unknown_location_raises():
    agent = build_default_agent()

    with pytest.raises(LocationNotFoundError):
        agent.run("Nowhereville, XX", "Would this be a good place for a college student?")


def test_davis_square_reports_coverage_gaps_honestly():
    agent = build_default_agent()

    response = agent.run("Davis Square, Somerville, MA", "Would this be a good place for a college student?")

    evidence_topics = {e.topic for e in response.evidence}
    assert evidence_topics == {"housing", "transportation"}  # only topics with fixture data

    missing_topic_limitations = [lim for lim in response.limitations if "No evidence was found" in lim]
    assert len(missing_topic_limitations) == 3  # safety, student_amenities, cost_of_living
    for topic_id in ("safety", "student_amenities", "cost_of_living"):
        assert any(topic_id in lim for lim in missing_topic_limitations)


def test_tool_call_budget_is_enforced():
    tight_config = AgentConfig(max_tool_calls=2)
    agent = build_default_agent(config=tight_config)

    response = agent.run("Harvard Square, Cambridge, MA", "Would this be a good place for a college student?")

    assert any("budget exhausted" in lim for lim in response.limitations)
