"""Baseline B: a simple search-and-summarize pipeline, for comparison against
the proposed adaptive agent (see docs/evaluation.md).

No topic decomposition, no retrieval scoring, no evidence storage, no claim
linking, no verification: one search call per question, and a "summary"
that is just the first few snippets concatenated — deliberately not using an
LLM, so this baseline is honest about being naive rather than a strawman
dressed up to look worse than it is. Baseline A (a plain LLM call with no
tools) is not implemented here — see the evaluation report in
docs/evaluation.md for what that means for these results' scope.
"""

from __future__ import annotations

import time

from app.core.config import TAVILY_API_KEY_ENV_VAR
from app.models.plan import Priority, ResearchTopic
from app.tools.base import LocationNotFoundError, ToolExecutionError
from app.tools.nominatim_tool import NominatimLocationResolverTool
from app.tools.tavily_tools import TavilyWebSearchTool
from evaluation.benchmark import BenchmarkCase
from evaluation.metrics import RunMetrics


def run_baseline_b(case: BenchmarkCase) -> RunMetrics:
    import os

    start = time.perf_counter()
    resolver = NominatimLocationResolverTool()

    try:
        location = resolver.resolve(case.location)
    except LocationNotFoundError as exc:
        return RunMetrics(
            case_id=case.case_id,
            system="baseline_b",
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

    query = f"{location.name} {location.city} {location.region} {case.question}"
    ad_hoc_topic = ResearchTopic(
        topic_id="general",
        reason="Baseline B does no topic decomposition; one query covers the whole question.",
        search_queries=[query],
        preferred_source_types=[],
        expected_evidence="Whatever the search API returns, unranked by this pipeline.",
        priority=Priority.MEDIUM,
        completion_criteria="n/a — no completion criteria in a single-shot search.",
    )

    search_tool = TavilyWebSearchTool(api_key=os.environ.get(TAVILY_API_KEY_ENV_VAR), max_results=5)
    try:
        evidence = search_tool.search(location, ad_hoc_topic)
    except ToolExecutionError as exc:
        return RunMetrics(
            case_id=case.case_id,
            system="baseline_b",
            succeeded=False,
            latency_seconds=time.perf_counter() - start,
            tool_calls=1,
            evidence_count=0,
            avg_relevance_score=None,
            source_type_diversity=0,
            topics_planned=None,
            topics_covered=None,
            claims_count=0,
            contradictions_detected=0,
            error=str(exc),
        )

    naive_summary = " ".join(e.text[:200] for e in evidence[:3])
    latency = time.perf_counter() - start

    return RunMetrics(
        case_id=case.case_id,
        system="baseline_b",
        succeeded=True,
        latency_seconds=latency,
        tool_calls=1,
        evidence_count=len(evidence),
        avg_relevance_score=None,  # Baseline B never scores relevance — it just consumes the API's raw order.
        source_type_diversity=len({e.source_type for e in evidence}),
        topics_planned=None,
        topics_covered=None,
        claims_count=0,
        contradictions_detected=0,
        notes=[f"Naive concatenated summary (no LLM): {naive_summary[:180]}"],
    )
