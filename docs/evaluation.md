# Evaluation Plan

No evaluation has been run yet. Milestone 1 has no LLM in its pipeline (see
`docs/architecture.md`), so Baseline A below doesn't yet have a meaningful counterpart to
compare against within this repo — this document is the plan for Milestone 2+, once an
LLM-backed planner/synthesizer exists, recorded now so evaluation isn't an afterthought.

## Comparisons

- **Baseline A** — a plain LLM call given only the location and question, no tools, no
  retrieval. Measures what the system adds over "just ask a model."
- **Baseline B** — a simple search-and-summarize pipeline: one search per question, summarize
  the top results, no topic planning, no claim/evidence linking, no verification.
- **Proposed system** — the full `LocationResearchAgent` pipeline: adaptive planning,
  retrieval, evidence storage, claim linking, and verification.

## Benchmark

A small, fixed set of location + question pairs, covering:

- A broad suitability question (the "college student" MVP case)
- A narrow single-topic question (e.g. nightlife-only, to check topics aren't over-selected)
- A location with only partial fixture coverage (to check coverage gaps are reported, not
  papered over)
- An unresolvable/unknown location (to check failure is explicit, not a hallucinated answer)

## Metrics

| Metric | How it's measured |
|---|---|
| Evidence relevance | Does retrieved evidence actually match the claimed topic? (manual judgment against `relevance_score`) |
| Citation correctness | Does every factual claim trace to a real `Evidence.source_url` and passage? |
| Groundedness | Are summary/recommendation statements traceable to `claims`/`evidence`, or is anything asserted without support? |
| Coverage of important topics | Fraction of planned topics that ended up with supported claims |
| Source quality | Distribution of `Evidence.quality_score` / `source_type` used |
| Recency handling | Are stale sources flagged (`recency_days` vs. `AgentConfig.stale_evidence_days`) rather than silently used? |
| Contradiction detection | Not yet implemented — tracked as a known gap, not scored as passing |
| Number of tool calls | From `research_trace` / the agent's internal call count vs. `AgentConfig.max_tool_calls` |
| Latency and token usage | Wall-clock time per run; token usage once an LLM is in the loop |
| Research completeness | Were all planned topics attempted before the budget ran out? |

## What would make Milestone 2 worth shipping

The proposed system should not be declared "better" until it is actually run against Baseline
A and B on the benchmark above and the metrics are reported — including cases where it loses
(e.g. higher latency, more tool calls, no clear groundedness improvement over Baseline B for a
trivial question). This document records the plan; it does not claim a result.
