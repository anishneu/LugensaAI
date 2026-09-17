"""The benchmark described in docs/evaluation.md, as actual runnable cases.

Deliberately small and fixed — this is not a claim that four cases are
statistically sufficient, only that they cover the categories the plan
calls for: a broad question, a narrow one, partial data coverage, and an
unresolvable location.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    location: str
    question: str
    category: str


BENCHMARK_CASES: list[BenchmarkCase] = [
    BenchmarkCase(
        case_id="broad_suitability",
        location="Harvard Square, Cambridge, MA",
        question="Would this be a good place for a college student?",
        category="broad multi-topic suitability question",
    ),
    BenchmarkCase(
        case_id="narrow_topic",
        location="Harvard Square, Cambridge, MA",
        question="What's the nightlife like around here?",
        category="narrow single-topic question",
    ),
    BenchmarkCase(
        case_id="partial_coverage",
        location="Davis Square, Somerville, MA",
        question="Would this be a good place for a college student?",
        category="location with only partial fixture coverage",
    ),
    BenchmarkCase(
        case_id="unresolvable_location",
        location="Nowhereville, XX",
        question="Would this be a good place for a college student?",
        category="unresolvable location — must fail explicitly, not hallucinate",
    ),
]
