"""Runs the actual LocationResearchAgent for the evaluation benchmark.

Uses live search (the same TavilyWebSearchTool Baseline B uses, for a fair
comparison of orchestration rather than search-quality differences) but not
the LLM-backed planner/extractor/synthesizer, so the benchmark measures
orchestration rather than model quality — see docs/evaluation.md for what that
means for claim-level metrics (there won't be any claims, on either system,
in this run).
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from app.agents.factory import build_default_agent
from app.models.claim import ClaimStatus
from app.models.trace import TraceStage
from app.tools.base import LocationNotFoundError
from evaluation.benchmark import BenchmarkCase
from evaluation.metrics import RunMetrics


def run_proposed_system(case: BenchmarkCase) -> RunMetrics:
    start = time.perf_counter()

    with tempfile.TemporaryDirectory() as tmp_dir:
        agent = build_default_agent(
            use_llm=False,
            use_live_search=True,
            use_semantic_retrieval=False,
            db_path=Path(tmp_dir) / "evidence.db",
        )
        try:
            response = agent.run(case.location, case.question)
        except LocationNotFoundError as exc:
            return RunMetrics(
                case_id=case.case_id,
                system="proposed",
                succeeded=False,
                latency_seconds=time.perf_counter() - start,
                tool_calls=0,
                evidence_count=0,
                avg_relevance_score=None,
                source_type_diversity=0,
                topics_planned=None,
                topics_covered=None,
                claims_count=0,
                contradictions_detected=0,
                error=str(exc),
                notes=["Location could not be resolved; correctly failed rather than guessing."],
            )

    latency = time.perf_counter() - start

    # The trace records one TOOL_SELECTION step per topic (one search call each);
    # each accepted evidence item corresponds to one page-retrieval call
    # (app/agents/location_research_agent.py always attempts one fetch per
    # accepted candidate). This is a derived estimate, not an exact counter.
    search_calls = sum(1 for step in response.research_trace if step.stage == TraceStage.TOOL_SELECTION)
    tool_calls = search_calls + len(response.evidence)

    relevance_scores = [e.relevance_score for e in response.evidence if e.relevance_score is not None]
    avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else None

    return RunMetrics(
        case_id=case.case_id,
        system="proposed",
        succeeded=True,
        latency_seconds=latency,
        tool_calls=tool_calls,
        evidence_count=len(response.evidence),
        avg_relevance_score=avg_relevance,
        source_type_diversity=len({e.source_type for e in response.evidence}),
        topics_planned=len(response.topics),
        topics_covered=len({e.topic for e in response.evidence}),
        claims_count=len(response.claims),
        contradictions_detected=sum(1 for c in response.claims if c.status == ClaimStatus.CONTRADICTED),
        notes=list(response.limitations[:3]),
    )
