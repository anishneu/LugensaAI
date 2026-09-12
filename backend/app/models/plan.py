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
    preferred_source_types: list[str] = Field(default_factory=list)
    expected_evidence: str = Field(..., description="What kind of evidence would satisfy this topic")
    priority: Priority = Priority.MEDIUM
    completion_criteria: str = Field(..., description="What counts as 'enough' evidence for this topic")


class ResearchPlan(BaseModel):
    """The structured decomposition of a question into research topics."""

    question: str
    detected_intents: list[str] = Field(default_factory=list)
    topics: list[ResearchTopic] = Field(default_factory=list)
