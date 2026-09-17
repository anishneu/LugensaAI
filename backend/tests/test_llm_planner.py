import json

from app.planning.llm_planner import LLMResearchPlanner
from app.planning.planner import KeywordResearchPlanner
from tests.llm_doubles import ScriptedLLMService


def test_llm_planner_selects_valid_topics(harvard_square):
    response = json.dumps(
        {
            "detected_intents": ["college_student"],
            "selected_topics": [
                {"topic_id": "housing", "reason": "Directly about where to live.", "priority": "high"},
                {"topic_id": "transportation", "reason": "Getting around matters.", "priority": "medium"},
            ],
        }
    )
    planner = LLMResearchPlanner(ScriptedLLMService([response]))

    plan = planner.plan(harvard_square, "Would this be a good place for a college student?")

    assert {t.topic_id for t in plan.topics} == {"housing", "transportation"}
    assert plan.detected_intents == ["college_student"]
    assert plan.notes == []
    housing = next(t for t in plan.topics if t.topic_id == "housing")
    assert housing.priority.value == "high"
    assert housing.search_queries  # still comes from the fixed taxonomy, not invented by the LLM


def test_llm_planner_ignores_unknown_topic_ids(harvard_square):
    response = json.dumps(
        {
            "detected_intents": [],
            "selected_topics": [
                {"topic_id": "made_up_topic", "reason": "nonsense", "priority": "high"},
                {"topic_id": "safety", "reason": "Safety matters.", "priority": "medium"},
            ],
        }
    )
    planner = LLMResearchPlanner(ScriptedLLMService([response]))

    plan = planner.plan(harvard_square, "Is it safe?")

    assert {t.topic_id for t in plan.topics} == {"safety"}
    assert any("unknown topic id" in note for note in plan.notes)


def test_llm_planner_falls_back_on_malformed_json(harvard_square):
    planner = LLMResearchPlanner(ScriptedLLMService(["not json at all"]), fallback=KeywordResearchPlanner())

    plan = planner.plan(harvard_square, "Would this be a good place for a college student?")

    assert {t.topic_id for t in plan.topics} == {
        "housing",
        "transportation",
        "safety",
        "student_amenities",
        "cost_of_living",
        "community_sentiment",
    }
    assert any("LLM-based planning failed" in note for note in plan.notes)


def test_llm_planner_falls_back_when_llm_errors(harvard_square):
    planner = LLMResearchPlanner(ScriptedLLMService(raise_error=True), fallback=KeywordResearchPlanner())

    plan = planner.plan(harvard_square, "What's the nightlife like?")

    assert {t.topic_id for t in plan.topics} == {"nightlife"}
    assert any("LLM-based planning failed" in note for note in plan.notes)


def test_llm_planner_falls_back_when_no_topics_selected(harvard_square):
    response = json.dumps({"detected_intents": [], "selected_topics": []})
    planner = LLMResearchPlanner(ScriptedLLMService([response]), fallback=KeywordResearchPlanner())

    plan = planner.plan(harvard_square, "Tell me about this place.")

    assert plan.topics  # the rule-based fallback bundle kicks in instead of an empty plan
    assert any("LLM-based planning failed" in note for note in plan.notes)
