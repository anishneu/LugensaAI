"""The agent's "look at what I have and decide what to do next" step.

Without this the research is one fixed pass: plan topics, search each once,
answer with whatever came back. A search that returned nothing useful simply
ended the run. This module is what makes the loop real. After the first pass a
`Reflector` looks at the question and at what evidence exists per topic and
chooses the next actions from a fixed menu of tools:

* `web_search`: search again with a new query aimed at the actual question
  (the first pass used fixed per-topic templates that never see it);
* `wikimedia`: consult Wikipedia/Wikivoyage for nearby landmarks and a travel
  guide, which is what a "is it worth visiting" question needs and reviews lack.

The choice is the model's when one is available (`LLMReflector`) and rule-based
otherwise (`RuleBasedReflector`). Either way the agent, not the model, executes
the actions: the model may only pick a tool from the menu, name one of the
planned topics, and phrase a query. Anything else is discarded. The loop is
bounded by `AgentConfig.max_research_rounds`, so it always terminates.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, Field

from app.core.llm_json import parse_json_object
from app.core.llm_service import LLMService, LLMServiceError
from app.models.evidence import Evidence
from app.models.location import Location
from app.models.plan import ResearchPlan

ToolName = Literal["web_search", "wikimedia"]

_TOOL_MENU: dict[str, str] = {
    "web_search": "Search the open web again with a new query. Use it when a topic has little or no evidence, "
    "or when the question asks about something the existing queries did not target.",
    "wikimedia": "Read Wikipedia articles about landmarks near the pin and the Wikivoyage travel guide for the "
    "town. Use it for visiting/tourism/what's-nearby questions, or when web search found nothing.",
}
_TRAVEL_RE = re.compile(
    r"\b(tourist|tourism|visit|visitor|visiting|travel|trip|sightsee\w*|attraction\w*|worth (?:a )?(?:visit|going|seeing)|"
    r"things to do|holiday|vacation|itinerary|nearby|around here)\b",
    re.IGNORECASE,
)
_MAX_QUERY_CHARS = 200


class ResearchAction(BaseModel):
    tool: ToolName
    topic_id: str
    query: str = Field(default="", description="For web_search: the query to run")
    reason: str = ""


class Reflection(BaseModel):
    enough: bool
    rationale: str
    actions: list[ResearchAction] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list, description="Transparency notes, surfaced as limitations")


def is_travel_question(question: str) -> bool:
    return bool(_TRAVEL_RE.search(question))


def question_query(location: Location, question: str) -> str:
    """A search query built from the user's own question plus the place, which
    the per-topic templates never include."""
    area = location.city or location.region or ""
    anchor = f'"{location.name}" {area}'.strip() if location.is_business else f"{location.name} {area}".strip()
    return f"{anchor} {question.strip()}"[:_MAX_QUERY_CHARS]


class Reflector(ABC):
    @abstractmethod
    def reflect(
        self,
        question: str,
        location: Location,
        plan: ResearchPlan,
        evidence: list[Evidence],
        tried_queries: set[str],
        available_tools: set[str],
        round_no: int,
    ) -> Reflection:
        raise NotImplementedError


def _evidence_by_topic(evidence: list[Evidence]) -> dict[str, list[Evidence]]:
    grouped: dict[str, list[Evidence]] = defaultdict(list)
    for item in evidence:
        grouped[item.topic].append(item)
    return grouped


class RuleBasedReflector(Reflector):
    """Deterministic judgement: search again for topics that came back empty,
    and consult Wikimedia for visiting questions or when nothing was found."""

    def reflect(self, question, location, plan, evidence, tried_queries, available_tools, round_no) -> Reflection:
        by_topic = _evidence_by_topic(evidence)
        actions: list[ResearchAction] = []
        query = question_query(location, question)

        empty_topics = [t for t in plan.topics if not by_topic.get(t.topic_id)]
        if "web_search" in available_tools and query not in tried_queries:
            for topic in empty_topics[:2]:
                actions.append(
                    ResearchAction(
                        tool="web_search",
                        topic_id=topic.topic_id,
                        query=query,
                        reason=f"No evidence yet for '{topic.topic_id}'; searching with the question itself.",
                    )
                )

        wants_reference = is_travel_question(question) or not evidence
        if "wikimedia" in available_tools and wants_reference and plan.topics:
            actions.append(
                ResearchAction(
                    tool="wikimedia",
                    topic_id=plan.topics[0].topic_id,
                    reason="A visiting/what's-nearby question is better served by a travel guide and nearby "
                    "landmarks than by reviews."
                    if is_travel_question(question)
                    else "Web search found nothing; checking Wikipedia/Wikivoyage.",
                )
            )

        if not actions:
            return Reflection(enough=True, rationale="Every planned topic has evidence; no further research needed.")
        return Reflection(
            enough=False,
            rationale=f"{len(empty_topics)} topic(s) without evidence"
            + ("; question concerns visiting" if is_travel_question(question) else ""),
            actions=actions,
        )


_SYSTEM_PROMPT = (
    "You are the decision step of a location research agent. It has already searched once. Look at the "
    "user's question and at what evidence was found per topic, then decide whether more research is needed "
    "and, if so, which tools to run next. Choose ONLY from the tools listed. Do not repeat a query that was "
    "already tried. Prefer no action when the evidence already answers the question. "
    "Respond with a single strict JSON object and nothing else."
)
_RESPONSE_SHAPE = (
    '{"enough": true | false, "rationale": "<one sentence>", "actions": [{"tool": "web_search" | "wikimedia", '
    '"topic_id": "<one of the planned topics>", "query": "<search query, for web_search only>", '
    '"reason": "<one sentence>"}]}'
)


class LLMReflector(Reflector):
    def __init__(self, llm: LLMService, fallback: Reflector | None = None, max_actions: int = 2) -> None:
        self._llm = llm
        self._fallback = fallback or RuleBasedReflector()
        self._max_actions = max_actions

    def reflect(self, question, location, plan, evidence, tried_queries, available_tools, round_no) -> Reflection:
        try:
            return self._reflect_with_llm(question, location, plan, evidence, tried_queries, available_tools)
        except (LLMServiceError, ValueError) as exc:
            fallback = self._fallback.reflect(
                question, location, plan, evidence, tried_queries, available_tools, round_no
            )
            fallback.notes.append(f"LLM-based research reflection failed ({exc}); used rule-based reflection.")
            return fallback

    def _reflect_with_llm(self, question, location, plan, evidence, tried_queries, available_tools) -> Reflection:
        by_topic = _evidence_by_topic(evidence)
        coverage = []
        for topic in plan.topics:
            items = by_topic.get(topic.topic_id, [])
            publishers = sorted({i.publisher or i.source_type.value for i in items})[:4]
            coverage.append(
                f"- {topic.topic_id}: {len(items)} source(s)" + (f" ({', '.join(publishers)})" if publishers else "")
            )
        tools = "\n".join(f"- {name}: {desc}" for name, desc in _TOOL_MENU.items() if name in available_tools)
        label = ", ".join(part for part in (location.name, location.city, location.region) if part)
        user_prompt = (
            f"Place: {label} ({'a specific business' if location.is_business else 'an area'})\n"
            f'Question: "{question}"\n\n'
            f"Evidence found so far, by planned topic:\n" + "\n".join(coverage) + "\n\n"
            f"Queries already tried:\n" + "\n".join(f"- {q}" for q in sorted(tried_queries)) + "\n\n"
            f"Tools you may choose:\n{tools}\n\n"
            f"Respond with JSON matching exactly this shape:\n{_RESPONSE_SHAPE}"
        )
        parsed = parse_json_object(self._llm.complete(_SYSTEM_PROMPT, user_prompt))

        topic_ids = {t.topic_id for t in plan.topics}
        notes: list[str] = []
        actions: list[ResearchAction] = []
        raw_actions = parsed.get("actions", [])
        if not isinstance(raw_actions, list):
            raise ValueError("'actions' must be a list")
        seen_queries = set(tried_queries)
        used_tools: set[str] = set()
        for raw in raw_actions:
            if not isinstance(raw, dict):
                continue
            tool, topic_id = raw.get("tool"), raw.get("topic_id")
            if tool not in available_tools:
                notes.append(f"Ignored a proposed research action with unavailable tool {tool!r}.")
                continue
            if topic_id not in topic_ids:
                topic_id = plan.topics[0].topic_id
            query = str(raw.get("query") or "").strip()[:_MAX_QUERY_CHARS]
            if tool == "web_search":
                if not query or query in seen_queries:
                    continue
                seen_queries.add(query)
            elif tool in used_tools:
                continue
            used_tools.add(tool)
            actions.append(
                ResearchAction(tool=tool, topic_id=topic_id, query=query, reason=str(raw.get("reason") or ""))
            )
            if len(actions) >= self._max_actions:
                break

        rationale = str(parsed.get("rationale") or "").strip() or "No rationale given."
        enough = bool(parsed.get("enough")) or not actions
        return Reflection(enough=enough, rationale=rationale, actions=[] if enough else actions, notes=notes)
