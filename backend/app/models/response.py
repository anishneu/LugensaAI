from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.claim import Claim
from app.models.evidence import Evidence
from app.models.location import Location
from app.models.plan import ResearchTopic
from app.models.trace import ResearchTraceStep


class ResearchResponse(BaseModel):
    """The final, structured output of a LocationResearchAgent run."""

    location: Location
    question: str
    summary: str
    key_findings: list[str] = Field(
        default_factory=list, description="Short, scannable bullet points directly answering the question"
    )
    details: str = Field(
        default="", description="Longer, question-organized elaboration citing sources and distinguishing fact from opinion"
    )
    recommendation: str
    topics: list[ResearchTopic]
    claims: list[Claim]
    evidence: list[Evidence]
    limitations: list[str] = Field(default_factory=list)
    research_trace: list[ResearchTraceStep] = Field(default_factory=list)
