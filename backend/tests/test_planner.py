from app.models.plan import Priority
from app.planning.planner import KeywordResearchPlanner
from app.planning.topics import FALLBACK_TOPIC_BUNDLE


def test_college_student_question_selects_persona_bundle(harvard_square):
    plan = KeywordResearchPlanner().plan(harvard_square, "Would this be a good place for a college student?")

    topic_ids = {t.topic_id for t in plan.topics}
    assert topic_ids == {
        "housing",
        "transportation",
        "safety",
        "student_amenities",
        "cost_of_living",
        "community_sentiment",
    }
    assert "college_student" in plan.detected_intents

    student_amenities = next(t for t in plan.topics if t.topic_id == "student_amenities")
    assert student_amenities.priority == Priority.HIGH  # explicitly mentioned via "student"


def test_nightlife_question_does_not_pull_in_housing(harvard_square):
    plan = KeywordResearchPlanner().plan(harvard_square, "What's the nightlife like around here?")

    topic_ids = {t.topic_id for t in plan.topics}
    assert topic_ids == {"nightlife"}
    assert "housing" not in topic_ids
    assert plan.topics[0].priority == Priority.HIGH


def test_generic_question_falls_back_to_general_bundle(harvard_square):
    plan = KeywordResearchPlanner().plan(harvard_square, "Tell me about this place.")

    topic_ids = {t.topic_id for t in plan.topics}
    assert topic_ids == set(FALLBACK_TOPIC_BUNDLE)
    assert "general_location_assessment" in plan.detected_intents
    assert all(t.priority == Priority.LOW for t in plan.topics)


def test_every_topic_has_queries_and_completion_criteria(harvard_square):
    plan = KeywordResearchPlanner().plan(harvard_square, "Would this be good for a college student?")

    for topic in plan.topics:
        assert topic.search_queries
        assert topic.completion_criteria
        assert topic.expected_evidence
        assert harvard_square.name in topic.reason


def test_a_specific_business_gets_queries_about_that_business_not_its_neighborhood(harvard_square):
    """Regression test: area-flavored queries ("... restaurants cafes food scene")
    for a single cafe returned roundups of other cafes in the same city."""
    business = harvard_square.model_copy(update={"name": "SR Coffee Roaster & Bar", "is_business": True})

    plan = KeywordResearchPlanner().plan(business, "How is the coffee and what do customers say in reviews?")

    queries = [q for topic in plan.topics for q in topic.search_queries]
    assert any('"SR Coffee Roaster & Bar"' in q and "reviews" in q for q in queries)
    assert not any("food scene" in q for q in queries)


def test_an_area_keeps_area_queries(harvard_square):
    plan = KeywordResearchPlanner().plan(harvard_square, "What are the restaurants and food like here?")

    assert any("food scene" in q for topic in plan.topics for q in topic.search_queries)


def test_transit_query_is_not_hardcoded_to_boston(harvard_square):
    plan = KeywordResearchPlanner().plan(harvard_square, "How is public transportation and commuting?")

    assert not any("MBTA" in q for topic in plan.topics for q in topic.search_queries)
