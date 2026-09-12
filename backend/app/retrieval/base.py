from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.evidence import Evidence


class EvidenceRetriever(ABC):
    @abstractmethod
    def score(self, candidates: list[Evidence], queries: list[str]) -> list[Evidence]:
        """Return `candidates` with `relevance_score` populated, sorted descending.

        Does not filter or truncate — that is the caller's responsibility,
        based on the run's configured threshold and per-topic evidence cap.
        """
        raise NotImplementedError
