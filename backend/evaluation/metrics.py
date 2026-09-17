"""Shared result shape for both systems under evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RunMetrics:
    case_id: str
    system: str
    succeeded: bool
    latency_seconds: float
    tool_calls: int
    evidence_count: int
    avg_relevance_score: float | None
    source_type_diversity: int
    topics_planned: int | None
    topics_covered: int | None
    claims_count: int
    contradictions_detected: int
    error: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_row(self) -> dict[str, str]:
        return {
            "case": self.case_id,
            "system": self.system,
            "ok": "yes" if self.succeeded else "NO",
            "latency_s": f"{self.latency_seconds:.2f}",
            "tool_calls": str(self.tool_calls),
            "evidence": str(self.evidence_count),
            "avg_relevance": "n/a" if self.avg_relevance_score is None else f"{self.avg_relevance_score:.2f}",
            "source_types": str(self.source_type_diversity),
            "topics_planned": "n/a" if self.topics_planned is None else str(self.topics_planned),
            "topics_covered": "n/a" if self.topics_covered is None else str(self.topics_covered),
            "claims": str(self.claims_count),
            "contradictions": str(self.contradictions_detected),
        }
