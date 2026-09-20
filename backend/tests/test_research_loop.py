"""The agent's decide-and-act loop: reflect on what was found, then choose the next tool."""

import json
from datetime import datetime, timezone

from app.agents.factory import build_default_agent
from app.agents.reflection import LLMReflector, Reflection, ResearchAction, Reflector, RuleBasedReflector, question_query
from app.models.evidence import Evidence, SourceType
from app.models.location import Location
from app.models.plan import Priority, ResearchPlan, ResearchTopic
from app.models.trace import TraceStage
from app.synthesis.llm_synthesizer import LLMSynthesizer
from app.tools.base import ToolExecutionError, WebSearchTool
from tests.llm_doubles import ScriptedLLMService

_LOCATION = Location(
    name="Suiran", city="Kurume", region="Fukuoka", country="Japan", slug="suiran",
    latitude=33.3253, longitude=130.6153, raw_query="Suiran", is_business=True,
)


def _topic(topic_id: str) -> ResearchTopic:
    return ResearchTopic(
        topic_id=topic_id, reason="r", search_queries=[f"first {topic_id} query"], expected_evidence="e",
        priority=Priority.HIGH, completion_criteria="c",
    )


def _plan(*topic_ids: str, question: str = "How are the reviews?") -> ResearchPlan:
    return ResearchPlan(question=question, topics=[_topic(t) for t in topic_ids])


def _evidence(topic: str, url: str = "https://example.org/a", text: str = "Some text about it.") -> Evidence:
    return Evidence(
        evidence_id=f"x:{topic}:{url[-3:]}", source_url=url, source_title="Title", publisher="Example",
        source_type=SourceType.BLOG, retrieved_at=datetime.now(timezone.utc), location_scope="Kurume",
        text=text, topic=topic,
    )


def _reflect(reflector: Reflector, question: str, plan: ResearchPlan, evidence=(), tools=("web_search", "wikimedia")):
    return reflector.reflect(question, _LOCATION, plan, list(evidence), set(), set(tools), 1)


# ---------------------------------------------------------------- rule-based


def test_rule_based_searches_again_with_the_question_for_a_topic_that_came_back_empty():
    reflection = _reflect(RuleBasedReflector(), "How is the coffee?", _plan("food", "community_sentiment"),
                          [_evidence("food")], tools=("web_search",))

    [action] = reflection.actions
    assert (action.tool, action.topic_id) == ("web_search", "community_sentiment")
    assert "How is the coffee?" in action.query and '"Suiran"' in action.query
    assert not reflection.enough


def test_rule_based_consults_wikimedia_for_a_visiting_question_even_when_web_search_found_things():
    reflection = _reflect(RuleBasedReflector(), "Is it a good place for a tourist to visit?", _plan("food"),
                          [_evidence("food")])

    assert [a.tool for a in reflection.actions] == ["wikimedia"]


def test_rule_based_stops_when_every_topic_has_evidence_and_the_question_is_not_about_visiting():
    reflection = _reflect(RuleBasedReflector(), "How is the coffee?", _plan("food"), [_evidence("food")])

    assert reflection.enough and not reflection.actions


def test_rule_based_does_not_repeat_a_query_already_tried():
    query = question_query(_LOCATION, "How is the coffee?")
    reflection = RuleBasedReflector().reflect(
        "How is the coffee?", _LOCATION, _plan("food"), [], {query}, {"web_search"}, 2
    )

    assert reflection.enough


# ---------------------------------------------------------------- LLM-driven


def _llm_reflector(*responses: str) -> LLMReflector:
    return LLMReflector(ScriptedLLMService(list(responses)))


def test_llm_reflector_can_choose_a_tool_a_topic_and_a_query():
    reply = json.dumps({"enough": False, "rationale": "Nothing on tourism.", "actions": [
        {"tool": "web_search", "topic_id": "food", "query": "Suiran Kurume tabelog", "reason": "find reviews"},
        {"tool": "wikimedia", "topic_id": "food", "query": "", "reason": "travel guide"}]})

    reflection = _reflect(_llm_reflector(reply), "Worth a visit?", _plan("food"))

    assert [(a.tool, a.query) for a in reflection.actions] == [("web_search", "Suiran Kurume tabelog"), ("wikimedia", "")]
    assert reflection.rationale == "Nothing on tourism."


def test_llm_reflector_discards_anything_outside_the_tool_menu_and_repeats():
    reply = json.dumps({"enough": False, "rationale": "x", "actions": [
        {"tool": "delete_database", "topic_id": "food", "query": "x"},
        {"tool": "web_search", "topic_id": "invented_topic", "query": "first food query"},
        {"tool": "web_search", "topic_id": "invented_topic", "query": "new query"}]})
    reflector = _llm_reflector(reply)

    reflection = reflector.reflect("q", _LOCATION, _plan("food"), [], {"first food query"}, {"web_search"}, 1)

    [action] = reflection.actions
    assert action.query == "new query" and action.topic_id == "food"  # unknown topic falls back to a planned one
    assert any("delete_database" in note for note in reflection.notes)


def test_llm_reflector_never_returns_more_actions_than_allowed():
    actions = [{"tool": "web_search", "topic_id": "food", "query": f"query {i}"} for i in range(6)]
    reflection = _reflect(_llm_reflector(json.dumps({"enough": False, "rationale": "x", "actions": actions})),
                          "q", _plan("food"))

    assert len(reflection.actions) == 2


def test_llm_reflector_says_enough_when_the_model_does():
    reply = json.dumps({"enough": True, "rationale": "Well covered.", "actions": []})

    assert _reflect(_llm_reflector(reply), "q", _plan("food"), [_evidence("food")]).enough


def test_llm_reflector_falls_back_to_rules_and_says_so_when_the_model_fails():
    reflector = LLMReflector(ScriptedLLMService(raise_error=True))

    reflection = _reflect(reflector, "Is it worth a visit as a tourist?", _plan("food"), [_evidence("food")])

    assert [a.tool for a in reflection.actions] == ["wikimedia"]
    assert any("rule-based reflection" in note for note in reflection.notes)


def test_llm_reflector_rejects_garbage_output_into_the_fallback():
    reflection = _reflect(_llm_reflector("not json at all"), "q", _plan("food"))

    assert any("rule-based reflection" in note for note in reflection.notes)


# ---------------------------------------------------------------- the agent


class _SearchThatFindsNothingFirst(WebSearchTool):
    """Empty on the first pass; a relevant page only for the question-shaped follow-up."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, location, topic):
        self.queries.append(topic.search_queries[0])
        if "location for a tourist" not in topic.search_queries[0]:
            return []
        return [_evidence(
            topic.topic_id, "https://example.org/kurume-visit",
            "Suiran seafood restaurant in Kurume: tourists and visitors recommend the seafood bowls and reviews say "
            "the customer reviews are positive, tourist friendly, with a location worth visiting.",
        )]


class _Wiki:
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self._fail = fail

    def lookup(self, location, question, topic_id):
        self.calls += 1
        if self._fail:
            raise ToolExecutionError("wikimedia is down")
        return [_evidence(topic_id, "https://en.wikivoyage.org/wiki/Kurume",
                          "Kurume travel guide: visitors and tourists enjoy the seafood bowls and reviews of restaurants "
                          "near Suiran, a location worth visiting for tourist travellers.")]


def _agent(search=None, wiki=None, reflector=None):
    agent = build_default_agent()
    agent.web_search_tool = search or _SearchThatFindsNothingFirst()
    agent.wiki_tool = wiki
    agent.reflector = reflector
    return agent


_QUESTION = "how are the customer reviews and is it a location for a tourist to visit?"


def test_without_a_reflector_the_run_is_a_single_pass():
    search = _SearchThatFindsNothingFirst()

    response = _agent(search).run(_LOCATION, _QUESTION)

    assert all(s.stage != TraceStage.ADDITIONAL_RESEARCH or "Round" not in s.description for s in response.research_trace)
    assert all("location for a tourist" not in q for q in search.queries)


def test_the_agent_searches_again_after_an_empty_first_pass_and_uses_what_it_finds():
    search = _SearchThatFindsNothingFirst()

    response = _agent(search, reflector=RuleBasedReflector()).run(_LOCATION, _QUESTION)

    assert any("location for a tourist" in q for q in search.queries), "a follow-up search using the question should have run"
    assert any(e.source_url == "https://example.org/kurume-visit" for e in response.evidence)
    decisions = [s for s in response.research_trace if "decision" in s.description]
    assert decisions and decisions[0].stage == TraceStage.ADDITIONAL_RESEARCH
    assert any(s.description.startswith("Ran web_search") for s in response.research_trace)


def test_the_agent_consults_wikimedia_when_the_reflector_chooses_it_and_cites_it():
    wiki = _Wiki()

    response = _agent(wiki=wiki, reflector=RuleBasedReflector()).run(_LOCATION, _QUESTION)

    assert wiki.calls == 1
    assert any(e.source_url == "https://en.wikivoyage.org/wiki/Kurume" for e in response.evidence)


def test_a_failing_tool_becomes_a_limitation_and_the_run_still_completes():
    response = _agent(wiki=_Wiki(fail=True), reflector=RuleBasedReflector()).run(_LOCATION, _QUESTION)

    assert any("wikimedia is down" in limitation for limitation in response.limitations)
    assert response.summary


class _AlwaysWantsMore(Reflector):
    def __init__(self) -> None:
        self.rounds = 0

    def reflect(self, question, location, plan, evidence, tried_queries, available_tools, round_no):
        self.rounds += 1
        return Reflection(
            enough=False, rationale="keep going",
            actions=[ResearchAction(tool="web_search", topic_id=plan.topics[0].topic_id,
                                    query=f"another query {self.rounds}", reason="more")],
        )


def test_the_loop_is_bounded_even_if_the_reflector_never_says_enough():
    reflector = _AlwaysWantsMore()
    agent = _agent(reflector=reflector)

    agent.run(_LOCATION, _QUESTION)

    assert reflector.rounds == agent.config.max_research_rounds == 2


def test_the_tool_call_budget_stops_the_loop():
    reflector = _AlwaysWantsMore()
    agent = _agent(reflector=reflector)
    agent.config = agent.config.model_copy(update={"max_tool_calls": 1})

    response = agent.run(_LOCATION, _QUESTION)

    assert reflector.rounds == 0
    assert any("budget exhausted" in limitation for limitation in response.limitations)


# ---------------------------------------------------- overview traceability


def test_an_overview_sentence_with_no_source_is_flagged_as_the_models_inference():
    invented = "It is an authentic upscale destination beloved by international gourmet travellers."
    reply = json.dumps({
        "summary": f"Reviews say the seafood bowls are positive. {invented}",
        "key_findings": ["Seafood bowls are liked"], "details": "d", "recommendation": "Consider going.",
    })
    agent = _agent(_SearchThatFindsNothingFirst(), reflector=RuleBasedReflector())
    agent.synthesizer = LLMSynthesizer(ScriptedLLMService([reply]))

    response = agent.run(_LOCATION, _QUESTION)

    flagged = [lim for lim in response.limitations if "could not be confirmed against any retrieved source" in lim]
    assert flagged and invented in flagged[0]
    assert "Reviews say the seafood bowls are positive" not in flagged[0]


def test_an_overview_sentence_that_merges_verified_claims_is_not_flagged():
    """Two supported claims combined into one sentence: no single source has all its words, but it is
    backed by claims that were each checked against their sources."""
    from app.models.claim import Claim, ClaimStatus
    from app.verification.support import untraceable_sentences

    claims = [
        Claim(claim_id="1", text="Diners praise the fresh seafood bowls and large sashimi pieces.", claim_type="food",
              status=ClaimStatus.SUPPORTED),
        Claim(claim_id="2", text="Some reviews mention long wait times during lunch.", claim_type="food",
              status=ClaimStatus.SUPPORTED),
    ]
    merged = "Diners praise the fresh seafood bowls and large sashimi pieces, though some reviews mention long wait times during lunch."
    invented = "It is beloved by international gourmet travellers seeking authentic upscale experiences."
    sources = ["Fresh seafood bowls with large sashimi pieces are praised.", "Long wait times at lunch.",
               " ".join(c.text for c in claims)]

    assert untraceable_sentences(merged, sources) == []
    assert untraceable_sentences(invented, sources) == [invented]
