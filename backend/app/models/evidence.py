from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SourceType(StrEnum):
    NEWS = "news"
    LOCAL_GOVERNMENT = "local_government"
    BUSINESS_DIRECTORY = "business_directory"
    REVIEW_AGGREGATOR = "review_aggregator"
    COMMUNITY_FORUM = "community_forum"
    ACADEMIC = "academic"
    BLOG = "blog"
    OTHER = "other"


class Evidence(BaseModel):
    """A single piece of source-grounded evidence.

    Preserves enough provenance to trace any claim back to the exact
    passage and source it came from.
    """

    evidence_id: str
    source_url: str
    source_title: str
    publisher: str | None = None
    source_type: SourceType
    retrieved_at: datetime = Field(..., description="When this pipeline run fetched the source")
    published_at: datetime | None = Field(default=None, description="When the source content was published, if known")
    location_scope: str = Field(..., description="Free-text geographic scope the source pertains to")
    text: str = Field(..., description="The exact extracted passage used as evidence")
    topic: str = Field(..., description="Research topic id this evidence was retrieved for")
    metadata: dict[str, str] = Field(default_factory=dict, description="Additional provenance/source metadata")
    relevance_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Set by the retriever; how well this matches the topic's queries"
    )
    quality_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Heuristic source-quality score, set during evidence processing"
    )
    recency_days: int | None = Field(
        default=None, description="Days between publication and retrieval, if publication date is known"
    )
