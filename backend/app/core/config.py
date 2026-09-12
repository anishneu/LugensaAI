from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class AgentConfig(BaseModel):
    """Bounded-loop and retrieval limits for a LocationResearchAgent run.

    These exist so the research loop is guaranteed to terminate and cannot
    run away making unbounded tool calls or hoarding unlimited evidence.
    """

    max_tool_calls: int = 30
    max_evidence_per_topic: int = 4
    min_relevance_score: float = 0.15
    stale_evidence_days: int = 730


BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_ROOT = BACKEND_ROOT / "fixtures"
