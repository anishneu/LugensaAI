from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class TraceStage(StrEnum):
    LOCATION_RESOLUTION = "location_resolution"
    QUESTION_UNDERSTANDING = "question_understanding"
    RESEARCH_PLANNING = "research_planning"
    TOOL_SELECTION = "tool_selection"
    RETRIEVAL = "retrieval"
    EVIDENCE_PROCESSING = "evidence_processing"
    COVERAGE_CHECK = "coverage_check"
    ADDITIONAL_RESEARCH = "additional_research"
    CLAIM_EXTRACTION = "claim_extraction"
    CLAIM_VERIFICATION = "claim_verification"
    SYNTHESIS = "synthesis"


class ResearchTraceStep(BaseModel):
    """One recorded step in the agent's execution, for transparency."""

    stage: TraceStage
    description: str
    timestamp: datetime
    details: dict[str, str] = Field(default_factory=dict)
