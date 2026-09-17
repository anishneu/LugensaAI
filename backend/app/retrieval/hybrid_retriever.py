"""Hybrid retrieval: blend keyword and semantic scores (Milestone 4).

Neither method subsumes the other: keyword matching is exact and cheap but
misses paraphrases; semantic matching catches paraphrases but can also drift
toward loosely-related passages that share no real overlap with the query's
intent. Blending them is a real, if simple, way to hedge between the two
failure modes rather than betting entirely on one. `keyword_weight` is not
tuned against any benchmark yet — that tuning is exactly what
`docs/evaluation.md` calls for before trusting this blend's exact ratio.
"""

from __future__ import annotations

from app.models.evidence import Evidence
from app.retrieval.base import EvidenceRetriever


class HybridEvidenceRetriever(EvidenceRetriever):
    def __init__(self, keyword: EvidenceRetriever, semantic: EvidenceRetriever, keyword_weight: float = 0.5) -> None:
        if not 0.0 <= keyword_weight <= 1.0:
            raise ValueError("keyword_weight must be between 0.0 and 1.0")
        self._keyword = keyword
        self._semantic = semantic
        self._keyword_weight = keyword_weight

    def score(self, candidates: list[Evidence], queries: list[str]) -> list[Evidence]:
        if not candidates:
            return []

        keyword_scores = {e.evidence_id: (e.relevance_score or 0.0) for e in self._keyword.score(candidates, queries)}
        semantic_scored = self._semantic.score(candidates, queries)

        blended: list[Evidence] = []
        for evidence in semantic_scored:
            keyword_score = keyword_scores.get(evidence.evidence_id, 0.0)
            semantic_score = evidence.relevance_score or 0.0
            combined = self._keyword_weight * keyword_score + (1 - self._keyword_weight) * semantic_score
            blended.append(evidence.model_copy(update={"relevance_score": round(combined, 3)}))

        blended.sort(key=lambda e: e.relevance_score or 0.0, reverse=True)
        return blended
