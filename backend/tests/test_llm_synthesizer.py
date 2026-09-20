import json
from datetime import datetime, timezone

from app.models.claim import Claim, ClaimStatus
from app.models.evidence import Evidence, SourceType
from app.models.location import Location
from app.models.plan import Priority, ResearchPlan, ResearchTopic
from app.synthesis.llm_synthesizer import LLMSynthesizer
from tests.llm_doubles import ScriptedLLMService


def _location() -> Location:
    return Location(
        name="Harvard Square",
        city="Cambridge",
        region="MA",
        country="US",
        slug="harvard-square-cambridge-ma",
        raw_query="Harvard Square",
    )


def _plan() -> ResearchPlan:
    return ResearchPlan(
        question="q",
        topics=[
            ResearchTopic(
                topic_id="housing",
                reason="r",
                search_queries=["q"],
                preferred_source_types=[],
                expected_evidence="e",
                priority=Priority.HIGH,
                completion_criteria="c",
            )
        ],
    )


def _claim(status: ClaimStatus = ClaimStatus.SUPPORTED) -> Claim:
    return Claim(claim_id="c1", text="Rent is high.", claim_type="housing", supporting_evidence_ids=["e1"], status=status)


def _evidence() -> list[Evidence]:
    return [
        Evidence(
            evidence_id="e1",
            source_url="https://example.org/e1",
            source_title="Housing report",
            source_type=SourceType.NEWS,
            retrieved_at=datetime.now(timezone.utc),
            location_scope="Cambridge, MA",
            text="Rent is high in this neighborhood.",
            topic="housing",
        )
    ]


def test_uses_llm_drafted_prose_plus_deterministic_limitations():
    response = json.dumps(
        {
            "summary": "Housing is expensive.",
            "key_findings": ["Rent is high"],
            "details": "Housing costs are elevated based on available evidence.",
            "recommendation": "It could work depending on your budget.",
        }
    )
    synthesizer = LLMSynthesizer(ScriptedLLMService([response]))

    result = synthesizer.synthesize(_location(), "q?", _plan(), [_claim()], _evidence())

    assert result.summary == "Housing is expensive."
    assert result.key_findings == ["Rent is high"]
    assert result.details == "Housing costs are elevated based on available evidence."
    assert result.recommendation == "It could work depending on your budget."
    assert any("contradiction detection" in lim.lower() for lim in result.limitations)


def test_falls_back_on_absolute_language():
    response = json.dumps(
        {"summary": "ok", "recommendation": "This is guaranteed to be perfect for everyone."}
    )
    synthesizer = LLMSynthesizer(ScriptedLLMService([response]))

    result = synthesizer.synthesize(_location(), "q?", _plan(), [_claim()], _evidence())

    assert any("LLM-based synthesis failed" in lim for lim in result.limitations)
    assert "guaranteed" not in result.recommendation.lower()


def test_falls_back_on_absolute_safety_language_in_details():
    response = json.dumps(
        {
            "summary": "ok",
            "details": "This area is completely safe and no crime has ever happened here.",
            "recommendation": "Seems fine.",
        }
    )
    synthesizer = LLMSynthesizer(ScriptedLLMService([response]))

    result = synthesizer.synthesize(_location(), "q?", _plan(), [_claim()], _evidence())

    assert any("LLM-based synthesis failed" in lim for lim in result.limitations)


def test_falls_back_on_llm_error():
    synthesizer = LLMSynthesizer(ScriptedLLMService(raise_error=True))

    result = synthesizer.synthesize(_location(), "q?", _plan(), [_claim()], _evidence())

    assert result.summary
    assert result.recommendation
    assert any("LLM-based synthesis failed" in lim for lim in result.limitations)


def test_missing_topic_limitation_present_even_if_llm_omits_it():
    plan = _plan()  # plans for 'housing' but is given zero claims below
    response = json.dumps({"summary": "No housing evidence found.", "recommendation": "Not enough data to say."})
    synthesizer = LLMSynthesizer(ScriptedLLMService([response]))

    result = synthesizer.synthesize(_location(), "q?", plan, [], [])

    assert any("No evidence was found for planned topic 'housing'" in lim for lim in result.limitations)


def test_strips_html_a_small_local_model_wraps_prose_in():
    """Regression test: llama3.2:3b returned `<p>...</p><p>...</p>` in `details`
    despite being asked for plain text, and the UI showed the raw tags."""
    response = json.dumps(
        {
            "summary": "<p>Reviews are mixed.</p>",
            "key_findings": ["<b>Mixed</b> reviews"],
            "details": "<p>First point.</p><p>Second &amp; third point.</p>",
            "recommendation": "Read recent reviews first.",
        }
    )
    synthesizer = LLMSynthesizer(ScriptedLLMService([response]))

    result = synthesizer.synthesize(_location(), "q?", _plan(), [_claim()], _evidence())

    assert result.summary == "Reviews are mixed."
    assert result.key_findings == ["Mixed reviews"]
    assert result.details == "First point.\n\nSecond & third point."
