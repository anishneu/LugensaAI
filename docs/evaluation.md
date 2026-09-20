# Evaluation Plan and Results

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
- A location with only partial coverage (to check coverage gaps are reported, not
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
| Contradiction detection | Implemented as a coarse keyword heuristic (`app/verification/contradiction.py`); not evaluated against labeled data, so no accuracy is claimed |
| Number of tool calls | From `research_trace` / the agent's internal call count vs. `AgentConfig.max_tool_calls` |
| Latency and token usage | Wall-clock time per run; token usage once an LLM is in the loop |
| Research completeness | Were all planned topics attempted before the budget ran out? |

## Results (Milestone 8, run 2026-09-16)

_Note added later: this run resolved locations with a fixture resolver that has since been removed
from the product; the harness now resolves through OpenStreetMap Nominatim. References below to
`FixtureClaimExtractor` and `fixtures/` describe the code as it was when the run was made._

Run via `python -m evaluation.run_benchmark` from `backend/` (code in `backend/evaluation/`).
Raw output: `backend/evaluation/last_run_results.json`. Reproducible with `TAVILY_API_KEY` set;
the LLM-backed components were not used for this run.

**Scope, stated plainly:**
- **Baseline A was not run.** It needs a real LLM call and was not implemented for this benchmark. Nothing below compares against it — the table only measures Baseline B vs.
  the proposed system's *orchestration* (planning, retrieval scoring, verification), not
  generation quality.
- **Citation correctness / groundedness / claim-level comparison could not be measured this
  run.** Both systems produced zero claims (`FixtureClaimExtractor` cannot extract from real
  page text — see `docs/research-workflow.md`). This is not evidence the systems are equal on
  those metrics; it's evidence they're both untestable on those metrics without an LLM key.
- **The `partial_coverage` case (Davis Square) did not exercise its intended fixture-gap
  behavior.** Both systems used live search here, and Tavily has no trouble finding real Davis
  Square results regardless of what's in `fixtures/`. The actual fixture-coverage-gap behavior
  (evidence found for only 2 of 5 planned topics, reported honestly) is verified separately and
  deterministically in `tests/test_agent_end_to_end.py::test_davis_square_reports_coverage_gaps_honestly`.
  This is a real gap in this benchmark's design, noted rather than glossed over.
- Both systems used the same live `TavilyWebSearchTool`, so the comparison isolates the
  orchestration layer (adaptive multi-topic planning + retrieval scoring + verification) from
  search-quality differences.

| case | system | ok | latency (s) | tool calls | evidence | avg relevance | source types | topics planned | topics covered |
|---|---|---|---|---|---|---|---|---|---|
| broad_suitability | baseline_b | yes | 2.07 | 1 | 5 | n/a | 4 | n/a | n/a |
| broad_suitability | proposed | yes | 9.48 | 25 | 20 | 0.55 | 4 | 5 | 5 |
| narrow_topic | baseline_b | yes | 1.79 | 1 | 5 | n/a | 3 | n/a | n/a |
| narrow_topic | proposed | yes | 3.33 | 5 | 4 | 0.64 | 1 | 1 | 1 |
| partial_coverage | baseline_b | yes | 3.43 | 1 | 5 | n/a | 3 | n/a | n/a |
| partial_coverage | proposed | yes | 8.15 | 25 | 20 | 0.54 | 2 | 5 | 5 |
| unresolvable_location | baseline_b | **NO** | 0.00 | 0 | 0 | n/a | 0 | n/a | n/a |
| unresolvable_location | proposed | **NO** | 0.01 | 0 | 0 | n/a | 0 | n/a | n/a |

**What this actually shows:**

- **Both systems correctly refuse to answer for an unresolvable location** rather than
  hallucinating a place — the one metric where "failure" in the `ok` column is the correct,
  desired outcome for both.
- **The proposed system reaches full topic coverage every time** (`topics_covered` ==
  `topics_planned` in both resolvable-and-relevant cases); Baseline B has no topic concept at
  all, so "coverage" isn't meaningful for it — it either finds something relevant to the whole
  question in one shot or it doesn't.
- **The proposed system is the only one that scores relevance at all** (`avg_relevance`
  0.54–0.64 vs. Baseline B's `n/a`). Baseline B just takes the search API's raw ranking
  on faith. This is the concrete, measured version of the "adaptive retrieval" claim in
  `docs/architecture.md` — not assumed, shown.
- **This costs real latency and tool calls.** The proposed system used 5–25x more tool calls
  and took roughly 2–4.5x longer than Baseline B in every resolvable case. Thoroughness is not
  free, and a system that needs one topic (`narrow_topic`) correctly does far less work (5 tool
  calls) than one needing five (`broad_suitability`/`partial_coverage`, 25 tool calls each,
  capped by `AgentConfig.max_evidence_per_topic`).
- **Not a clean win on every axis:** in `narrow_topic`, the proposed system's single
  hyper-specific query returned evidence from only 1 source type, while Baseline B's single
  broader query happened to pull from 3. A narrowly-targeted query can trade source diversity
  for precision — a real, unflattering data point, not hidden here.

## Worldwide coverage probe (not a benchmark)

`python -m evaluation.global_coverage` resolves 16 places on every inhabited continent (some typed in
their own script) and reports, per place, whether the pin lands within a tolerance of the true
coordinates, what web search returns and in which language, and what OpenStreetMap, Wikipedia and
Wikivoyage add. It found nine defects that a two-neighborhood test could not (listed in
`backend/README.md`, "Working in any country"); after fixing them: pins 16 of 16 within tolerance
(was 14 of 15), any non-English source for 7 of 16 places (was 1 of 15). It says whether each stage
returns something plausible, not whether the final answer is correct; no answer-quality benchmark
has been run outside the original two neighborhoods. Add your own places to `PLACES`.

## What's still needed before claiming more

Baseline A, and any claim-level metric (citation correctness, groundedness, coverage of
*supported* topics rather than just topics-with-evidence), need the LLM-backed components on (`OLLAMA_ENABLED`) and the
benchmark re-run with `use_llm=True`. Until then, the honest claim is narrower than "the agent
is better": *the orchestration layer measurably improves topic coverage and adds relevance
scoring Baseline B entirely lacks, at a real and measured latency/tool-call cost* — nothing has
been shown yet about whether its eventual LLM-generated answers are more grounded or accurate
than Baseline A's or B's.
