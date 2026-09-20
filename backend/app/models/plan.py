from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Priority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ResearchTopic(BaseModel):
    """One planned line of investigation within a research plan."""

    topic_id: str = Field(..., description="Stable topic identifier, e.g. 'housing'")
    reason: str = Field(..., description="Why this topic is relevant to the question")
    search_queries: list[str] = Field(default_factory=list)
    local_queries: list[str] = Field(
        default_factory=list,
        description="The same research in the place's own language. Used by the search tool only, never for "
        "relevance scoring: the retrievers score English text against English queries.",
    )
    preferred_source_types: list[str] = Field(default_factory=list)
    expected_evidence: str = Field(..., description="What kind of evidence would satisfy this topic")
    priority: Priority = Priority.MEDIUM
    completion_criteria: str = Field(..., description="What counts as 'enough' evidence for this topic")


class ResearchPlan(BaseModel):
    """The structured decomposition of a question into research topics."""

    question: str
    detected_intents: list[str] = Field(default_factory=list)
    topics: list[ResearchTopic] = Field(default_factory=list)
    notes: list[str] = Field(
        default_factory=list,
        description="Transparency notes about how the plan was produced, e.g. an LLM planning "
        "failure that caused a fallback to the rule-based planner. Surfaced in the final "
        "response's limitations.",
    )
