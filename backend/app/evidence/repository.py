from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.evidence import Evidence


class EvidenceRepository(ABC):
    @abstractmethod
    def add(self, evidence: Evidence) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, evidence_id: str) -> Evidence | None:
        raise NotImplementedError

    @abstractmethod
    def list_all(self) -> list[Evidence]:
        raise NotImplementedError

    @abstractmethod
    def list_by_topic(self, topic_id: str) -> list[Evidence]:
        raise NotImplementedError

    def add_all(self, evidence_items: list[Evidence]) -> None:
        for item in evidence_items:
            self.add(item)

    def close(self) -> None:
        """Release any underlying resources (e.g. a database connection). No-op by default."""
        return None


class InMemoryEvidenceRepository(EvidenceRepository):
    """A per-run evidence store. Not persisted across process restarts.

    Sufficient for Milestone 1, where each research run is stateless.
    A later milestone can swap this for a Postgres-backed implementation
    without changing anything that depends on the EvidenceRepository interface.
    """

    def __init__(self) -> None:
        self._items: dict[str, Evidence] = {}

    def add(self, evidence: Evidence) -> None:
        self._items[evidence.evidence_id] = evidence

    def get(self, evidence_id: str) -> Evidence | None:
        return self._items.get(evidence_id)

    def list_all(self) -> list[Evidence]:
        return list(self._items.values())

    def list_by_topic(self, topic_id: str) -> list[Evidence]:
        return [e for e in self._items.values() if e.topic == topic_id]
