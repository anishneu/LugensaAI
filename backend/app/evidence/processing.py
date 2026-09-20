"""Evidence enrichment: turning raw retrieved evidence into scored evidence.

Separate from retrieval (`app/retrieval/`) on purpose: retrieval decides how
well evidence matches a query, this decides properties of the evidence
itself (source quality, how stale it is) that don't depend on any query.
"""

from __future__ import annotations

from app.models.evidence import Evidence, SourceType

_SOURCE_TYPE_QUALITY: dict[SourceType, float] = {
    SourceType.LOCAL_GOVERNMENT: 0.9,
    SourceType.ACADEMIC: 0.9,
    SourceType.NEWS: 0.8,
    SourceType.REFERENCE: 0.7,
    SourceType.BUSINESS_DIRECTORY: 0.6,
    SourceType.REVIEW_AGGREGATOR: 0.6,
    SourceType.COMMUNITY_FORUM: 0.5,
    SourceType.BLOG: 0.5,
    SourceType.OTHER: 0.4,
}


def enrich_evidence(evidence: Evidence) -> Evidence:
    """Set `quality_score` and `recency_days` on a piece of evidence.

    `quality_score` is a coarse, explainable heuristic keyed on source type —
    not a learned or calibrated model. It is a documented placeholder for a
    more rigorous source-credibility assessment later.
    """
    recency_days = None
    if evidence.published_at is not None:
        recency_days = (evidence.retrieved_at - evidence.published_at).days
    quality_score = _SOURCE_TYPE_QUALITY.get(evidence.source_type, 0.4)
    return evidence.model_copy(update={"recency_days": recency_days, "quality_score": quality_score})
