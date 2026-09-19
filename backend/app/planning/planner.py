"""Research planning: turning a question into a structured ResearchPlan.

`KeywordResearchPlanner` is intentionally rule-based (no LLM) so Milestone 1
needs no API key. It still demonstrates real adaptivity: a question that
only mentions nightlife does not pull in housing research, and an explicit
topic mention always outranks a persona-bundle topic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.location import Location
from app.models.plan import Priority, ResearchPlan, ResearchTopic
from app.planning.topics import FALLBACK_TOPIC_BUNDLE, PERSONA_DEFINITIONS, TOPIC_DEFINITIONS, TopicDefinition


class ResearchPlanner(ABC):
    @abstractmethod
    def plan(self, location: Location, question: str) -> ResearchPlan:
        raise NotImplementedError


class KeywordResearchPlanner(ResearchPlanner):
    def plan(self, location: Location, question: str) -> ResearchPlan:
        normalized = question.lower()
        intents: list[str] = []
        topic_priority: dict[str, Priority] = {}

        for topic_id, definition in TOPIC_DEFINITIONS.items():
            if any(keyword in normalized for keyword in definition.keywords):
                topic_priority[topic_id] = Priority.HIGH

        for persona in PERSONA_DEFINITIONS.values():
            if any(keyword in normalized for keyword in persona.trigger_keywords):
                intents.append(persona.persona_id)
                for topic_id in persona.topic_bundle:
                    topic_priority.setdefault(topic_id, Priority.MEDIUM)

        if not topic_priority:
            intents.append("general_location_assessment")
            for topic_id in FALLBACK_TOPIC_BUNDLE:
                topic_priority.setdefault(topic_id, Priority.LOW)

        topics = [
            self._build_topic(location, TOPIC_DEFINITIONS[topic_id], priority)
            for topic_id, priority in topic_priority.items()
        ]
        return ResearchPlan(question=question, detected_intents=intents, topics=topics)

    @staticmethod
    def _build_topic(location: Location, definition: TopicDefinition, priority: Priority) -> ResearchTopic:
        location_label = f"{location.name}, {location.city}, {location.region}".strip(", ")
        return ResearchTopic(
            topic_id=definition.topic_id,
            reason=definition.reason_template.format(location=location.name),
            search_queries=definition.queries_for(
                location_label, location.is_business, location.name, location.city or location.region or ""
            ),
            preferred_source_types=list(definition.preferred_source_types),
            expected_evidence=definition.expected_evidence,
            priority=priority,
            completion_criteria=definition.completion_criteria,
        )
