import json

from app.models.claim import Claim, ClaimStatus
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


def test_uses_llm_drafted_prose_plus_deterministic_limitations():
    response = json.dumps(
        {"summary": "Housing is expensive.", "recommendation": "It could work depending on your budget."}
    )
    synthesizer = LLMSynthesizer(ScriptedLLMService([response]))

    summary, recommendation, limitations = synthesizer.synthesize(_location(), "q?", _plan(), [_claim()])

    assert summary == "Housing is expensive."
    assert recommendation == "It could work depending on your budget."
    assert any("contradiction detection" in lim.lower() for lim in limitations)


def test_falls_back_on_absolute_language():
    response = json.dumps(
        {"summary": "ok", "recommendation": "This is guaranteed to be perfect for everyone."}
    )
    synthesizer = LLMSynthesizer(ScriptedLLMService([response]))

    summary, recommendation, limitations = synthesizer.synthesize(_location(), "q?", _plan(), [_claim()])

    assert any("LLM-based synthesis failed" in lim for lim in limitations)
    assert "guaranteed" not in recommendation.lower()


def test_falls_back_on_llm_error():
    synthesizer = LLMSynthesizer(ScriptedLLMService(raise_error=True))

    summary, recommendation, limitations = synthesizer.synthesize(_location(), "q?", _plan(), [_claim()])

    assert summary
    assert recommendation
    assert any("LLM-based synthesis failed" in lim for lim in limitations)


def test_missing_topic_limitation_present_even_if_llm_omits_it():
    plan = _plan()  # plans for 'housing' but is given zero claims below
    response = json.dumps({"summary": "No housing evidence found.", "recommendation": "Not enough data to say."})
    synthesizer = LLMSynthesizer(ScriptedLLMService([response]))

    summary, recommendation, limitations = synthesizer.synthesize(_location(), "q?", plan, [])

    assert any("No evidence was found for planned topic 'housing'" in lim for lim in limitations)
