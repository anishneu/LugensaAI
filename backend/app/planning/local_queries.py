"""Search queries written in the place's own language.

The first pass searches in English. For a place in a country whose web is
written in another language, this adds one query per (up to three) topics in
that language, using the place's native-script name. Results come back through
the same translation and relevance filters as everything else.

With a model, it writes the whole query (topic words included) in the target
language: the plan's topic descriptions are English, and a query is only as good
as its vocabulary. Without one, it falls back to the native name and city alone,
which still finds the right place's local pages but no topic-specific ones.
The model may not drop the place from a query: one that omits both the native
name and the native city is discarded.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.llm_json import parse_json_object
from app.core.llm_service import LLMService, LLMServiceError
from app.models.location import Location
from app.models.plan import ResearchPlan
from app.tools.locale import LANGUAGE_NAMES

_MAX_TOPICS = 3
_MAX_QUERY_CHARS = 120


class LocalQueryWriter(ABC):
    @abstractmethod
    def write(self, location: Location, plan: ResearchPlan) -> dict[str, str]:
        """topic_id -> query in the location's local language (possibly empty)."""


def _place_words(location: Location) -> list[str]:
    return [w for w in (location.local_name, location.local_area) if w]


class RuleBasedLocalQueryWriter(LocalQueryWriter):
    def write(self, location: Location, plan: ResearchPlan) -> dict[str, str]:
        words = list(dict.fromkeys(_place_words(location)))
        if not words or not plan.topics:
            return {}
        # The same query for every topic would only repeat a search; one is enough.
        return {plan.topics[0].topic_id: " ".join(words)}


_SYSTEM_PROMPT = (
    "You write web search queries for a location research agent, in a specified language. Use the place's "
    "native-language name exactly as given. Each query should be short (a few words), the way a local would "
    "type it into a search engine, and aimed at the topic's goal. Respond with a single strict JSON object "
    "and nothing else."
)


class LLMLocalQueryWriter(LocalQueryWriter):
    def __init__(self, llm: LLMService, fallback: LocalQueryWriter | None = None) -> None:
        self._llm = llm
        self._fallback = fallback or RuleBasedLocalQueryWriter()

    def write(self, location: Location, plan: ResearchPlan) -> dict[str, str]:
        try:
            queries = self._write_with_llm(location, plan)
        except (LLMServiceError, ValueError):
            queries = {}
        return queries or self._fallback.write(location, plan)

    def _write_with_llm(self, location: Location, plan: ResearchPlan) -> dict[str, str]:
        language = LANGUAGE_NAMES.get(location.language or "", location.language or "the local language")
        topics = plan.topics[:_MAX_TOPICS]
        goals = "\n".join(f"- {t.topic_id}: {t.expected_evidence}" for t in topics)
        user_prompt = (
            f"Language: {language}\n"
            f"Place (English name): {location.name}, {location.city or ''}\n"
            f"Place (native name): {location.local_name or 'unknown'}\n"
            f"City (native name): {location.local_area or 'unknown'}\n"
            f"Kind: {'a specific business' if location.is_business else 'an area or landmark'}\n"
            f'User question: "{plan.question}"\n\n'
            f"Topics, and what each query should find:\n{goals}\n\n"
            'Respond with JSON matching exactly: {"queries": {"<topic_id>": "<query in the language>"}}'
        )
        parsed = parse_json_object(self._llm.complete(_SYSTEM_PROMPT, user_prompt))
        raw = parsed.get("queries")
        if not isinstance(raw, dict):
            raise ValueError("'queries' must be an object")

        anchors = _place_words(location)
        valid_topics = {t.topic_id for t in topics}
        queries: dict[str, str] = {}
        for topic_id, query in raw.items():
            if topic_id not in valid_topics or not isinstance(query, str):
                continue
            query = query.strip()[:_MAX_QUERY_CHARS]
            # Without the place in it a query is about the topic anywhere in the world.
            if query and (not anchors or any(anchor in query for anchor in anchors)):
                queries[topic_id] = query
        return queries
