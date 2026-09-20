"""LLM-backed research planning (Milestone 2).

Replaces `KeywordResearchPlanner`'s literal keyword matching with real
language understanding for topic *selection and rationale* — e.g. it can
recognize "Is it easy to get around without a car?" implies transportation
even though the words "transit" or "transportation" never appear.

The LLM does not get to invent topics or their queries/completion criteria:
it must choose from the fixed `TOPIC_DEFINITIONS` taxonomy, and everything
about how a chosen topic is researched still comes from that taxonomy. This
keeps topic selection subject to real judgment while keeping what happens
once a topic is selected fully deterministic and grounded in the tools this
agent actually has.

If the LLM call fails, times out, or returns output that doesn't validate
(unparseable JSON, no valid topic ids), this falls back to
`KeywordResearchPlanner` and records why in `ResearchPlan.notes` rather than
crashing the research run.
"""

from __future__ import annotations

from app.core.llm_json import parse_json_object
from app.core.llm_service import LLMService, LLMServiceError
from app.models.location import Location
from app.models.plan import Priority, ResearchPlan, ResearchTopic
from app.planning.planner import KeywordResearchPlanner, ResearchPlanner
from app.planning.topics import TOPIC_DEFINITIONS, TopicDefinition

_SYSTEM_PROMPT = (
    "You are the research-planning component of a location research agent. Given a place and a "
    "user's question about it, decide which research topics from the provided fixed list are "
    "relevant to answering that specific question. Do not select topics that are not relevant "
    "just because they seem generally useful — a question about one narrow thing should usually "
    "select very few topics. Respond with a single strict JSON object and nothing else: no "
    "markdown fences, no commentary before or after."
)

_RESPONSE_SHAPE = (
    '{"detected_intents": ["<short_snake_case_label>", ...], '
    '"selected_topics": [{"topic_id": "<one of the given topic ids>", '
    '"reason": "<one sentence, specific to this question>", '
    '"priority": "high" | "medium" | "low"}, ...]}'
)


def _topic_catalog_text() -> str:
    lines = []
    for topic_id, definition in TOPIC_DEFINITIONS.items():
        lines.append(f"- {topic_id}: {definition.expected_evidence}")
    return "\n".join(lines)


class LLMResearchPlanner(ResearchPlanner):
    def __init__(self, llm: LLMService, fallback: ResearchPlanner | None = None) -> None:
        self._llm = llm
        self._fallback = fallback or KeywordResearchPlanner()

    def plan(self, location: Location, question: str) -> ResearchPlan:
        try:
            return self._plan_with_llm(location, question)
        except (LLMServiceError, ValueError) as exc:
            fallback_plan = self._fallback.plan(location, question)
            fallback_plan.notes.append(
                f"LLM-based planning failed ({exc}); fell back to the rule-based planner."
            )
            return fallback_plan

    def _plan_with_llm(self, location: Location, question: str) -> ResearchPlan:
        location_label = f"{location.name}, {location.city}, {location.region}".strip(", ")
        user_prompt = (
            f"Location: {location_label}\n"
            f'Question: "{question}"\n\n'
            f"Available topics (topic_id: what evidence it covers):\n{_topic_catalog_text()}\n\n"
            f"Respond with JSON matching exactly this shape:\n{_RESPONSE_SHAPE}"
        )

        raw = self._llm.complete(_SYSTEM_PROMPT, user_prompt)
        parsed = parse_json_object(raw)

        detected_intents = [str(i) for i in parsed.get("detected_intents", []) if isinstance(i, (str, int, float))]
        raw_selected = parsed.get("selected_topics", [])
        if not isinstance(raw_selected, list):
            raise ValueError("'selected_topics' must be a list")

        notes: list[str] = []
        topics: list[ResearchTopic] = []
        for entry in raw_selected:
            if not isinstance(entry, dict):
                continue
            topic_id = entry.get("topic_id")
            definition = TOPIC_DEFINITIONS.get(topic_id)
            if definition is None:
                notes.append(f"LLM planner suggested unknown topic id '{topic_id}'; ignored.")
                continue

            priority_raw = str(entry.get("priority", "medium")).lower()
            try:
                priority = Priority(priority_raw)
            except ValueError:
                priority = Priority.MEDIUM

            reason = entry.get("reason") or definition.reason_template.format(location=location.name)
            topics.append(self._build_topic(location, location_label, definition, reason, priority))

        if not topics:
            raise ValueError("LLM planner returned no valid topics")

        return ResearchPlan(question=question, detected_intents=detected_intents, topics=topics, notes=notes)

    @staticmethod
    def _build_topic(
        location: Location, location_label: str, definition: TopicDefinition, reason: str, priority: Priority
    ) -> ResearchTopic:
        return ResearchTopic(
            topic_id=definition.topic_id,
            reason=reason,
            search_queries=definition.queries_for(
                location_label, location.is_business, location.name, location.city or location.region or ""
            ),
            preferred_source_types=list(definition.preferred_source_types),
            expected_evidence=definition.expected_evidence,
            priority=priority,
            completion_criteria=definition.completion_criteria,
        )
