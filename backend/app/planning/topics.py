"""The topic taxonomy the rule-based planner selects from.

Milestone 2 is expected to replace topic *selection* with an LLM call, but
even then this taxonomy (or something like it) is useful as a controlled
vocabulary the LLM chooses from, rather than letting it invent arbitrary
topic ids.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TopicDefinition:
    topic_id: str
    keywords: tuple[str, ...]
    reason_template: str
    query_templates: tuple[str, ...]
    preferred_source_types: tuple[str, ...]
    expected_evidence: str
    completion_criteria: str


@dataclass(frozen=True)
class PersonaDefinition:
    persona_id: str
    trigger_keywords: tuple[str, ...]
    topic_bundle: tuple[str, ...] = field(default_factory=tuple)


TOPIC_DEFINITIONS: dict[str, TopicDefinition] = {
    td.topic_id: td
    for td in [
        TopicDefinition(
            topic_id="housing",
            keywords=("housing", "rent", "apartment", "lease", "afford to live"),
            reason_template="The question concerns living in {location}, so housing availability and cost are relevant.",
            query_templates=("{location} student housing rent prices",),
            preferred_source_types=("local_government", "news", "business_directory"),
            expected_evidence="Rent ranges, housing availability, and any student-housing-specific programs.",
            completion_criteria="At least one source with concrete rent or availability information.",
        ),
        TopicDefinition(
            topic_id="transportation",
            keywords=("transportation", "transit", "commute", "bus", "train", "subway", "bike", "walkable", "mbta"),
            reason_template="Getting around {location} without a car matters for most college students.",
            query_templates=("{location} public transportation MBTA commute options",),
            preferred_source_types=("local_government", "news"),
            expected_evidence="Availability and quality of public transit, walkability, or bike infrastructure.",
            completion_criteria="At least one source describing available transit options.",
        ),
        TopicDefinition(
            topic_id="safety",
            keywords=("safe", "safety", "crime", "dangerous"),
            reason_template="Personal safety in {location} is a baseline concern for anyone considering living there.",
            query_templates=("{location} crime statistics safety report",),
            preferred_source_types=("local_government", "news"),
            expected_evidence="Crime statistics or safety assessments from an official or news source.",
            completion_criteria="At least one source with crime data or an official safety assessment.",
        ),
        TopicDefinition(
            topic_id="student_amenities",
            keywords=("student", "university", "college", "campus", "library", "study spot", "undergrad"),
            reason_template="The question is specifically about student life in {location}, so student-oriented amenities matter.",
            query_templates=("{location} student amenities library study spaces campus resources",),
            preferred_source_types=("academic", "business_directory", "news"),
            expected_evidence="Presence of libraries, study spaces, campus resources, or student services.",
            completion_criteria="At least one source describing a student-relevant amenity.",
        ),
        TopicDefinition(
            topic_id="cost_of_living",
            keywords=("cost of living", "expensive", "afford", "cheap", "prices", "budget"),
            reason_template="Affordability in {location} directly affects whether a student on a limited budget can live there.",
            query_templates=("{location} cost of living for students",),
            preferred_source_types=("news", "local_government"),
            expected_evidence="General cost-of-living data or comparisons relevant to a student budget.",
            completion_criteria="At least one source with cost-of-living information.",
        ),
        TopicDefinition(
            topic_id="nightlife",
            keywords=("nightlife", "bars", "clubs", "party", "going out", "night out"),
            reason_template="The question raises nightlife specifically, so bars/venues/late-night options in {location} are relevant.",
            query_templates=("{location} nightlife bars venues",),
            preferred_source_types=("review_aggregator", "business_directory"),
            expected_evidence="Presence and character of bars, clubs, or late-night venues.",
            completion_criteria="At least one source describing nightlife venues.",
        ),
        TopicDefinition(
            topic_id="food",
            keywords=("restaurants", "food scene", "dining", "cafes", "coffee"),
            reason_template="The question raises food/dining, so the local restaurant and cafe scene in {location} is relevant.",
            query_templates=("{location} restaurants cafes food scene",),
            preferred_source_types=("review_aggregator", "business_directory"),
            expected_evidence="Variety and affordability of restaurants and cafes.",
            completion_criteria="At least one source describing the local food scene.",
        ),
        TopicDefinition(
            topic_id="community_sentiment",
            keywords=("community", "locals", "reddit", "residents think", "opinion of"),
            reason_template="The question asks about community perception of {location}, which is subjective and best sourced from resident discussion.",
            query_templates=("{location} resident community discussion opinions",),
            preferred_source_types=("community_forum", "blog"),
            expected_evidence="Resident or community sentiment, clearly separated from objective fact.",
            completion_criteria="At least one community-forum or blog source.",
        ),
    ]
}

PERSONA_DEFINITIONS: dict[str, PersonaDefinition] = {
    pd.persona_id: pd
    for pd in [
        PersonaDefinition(
            persona_id="college_student",
            trigger_keywords=("college student", "university student", "undergrad", "grad student", "student"),
            topic_bundle=("housing", "transportation", "safety", "student_amenities", "cost_of_living"),
        ),
    ]
}

FALLBACK_TOPIC_BUNDLE: tuple[str, ...] = ("housing", "transportation", "safety")
