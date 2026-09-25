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

## Answer quality with the local model, on frozen sources (run 2026-09-25)

The section above measured the orchestration without a model. This one measures the answers, with the local model
(`qwen3:30b` through Ollama), which was the gap it named. `python -m evaluation.answer_quality` (code in
`backend/evaluation/`) answers ten questions three ways, all reading **the same frozen set of real sources**, so the
comparison is about what is done with the sources and not about what a search happened to return:

- **A**: the model alone, given the place and the question. What a plain chat model says.
- **B**: the model handed every source's text in one prompt, asked to answer from them and cite by number. Retrieval-augmented
  generation with none of the pipeline's checks.
- **PIPELINE**: the real agent: planning, relevance ranking, claim extraction with citations, deterministic verification,
  synthesis.

**The ten cases** (`quality_cases.py`) differ in what the free sources can reach: two questions about Harvard Square, a broad one
for Manchester's Northern Quarter, safety in Shibuya, tourism in Gion, food in Taipei's Zhongshan District, a weekend in Erfurt,
a family in Kurume, a night walk on Hunts Bank, and the reviews of a cafe. The sources per case were collected once on
2026-09-25 from what is free: Wikipedia and Wikivoyage around the pin, the free Reddit archive, and Google News' RSS (headlines,
English edition). Each corpus has 4 to 40 items (Erfurt 4, Tatte 13, Hunts Bank 15, the rest 34 to 40). **No search credit was
spent, and no model but the local one was used.** The corpora are third parties' text, so they stay local (gitignored); the
code and the measurements are committed (`answer_quality_results.json`, which holds no source or answer text).

**The measures are all deterministic; no model judges another** (`quality_metrics.py`, unit-tested):

1. *Sentences no source backs*: the share of an answer's sentences that no single source covers (half its content words, and
   every figure). This is the pipeline's own overview check, so it is the measure the pipeline is built to pass.
2. *Figures and names in no source*: numbers and multi-word names ("Red Line") that appear in none of the sources, the question,
   the place's name, or the sources' provenance (publisher, date, license line). A different method from (1). "In no source" is
   not "false": a model can know things the sources do not say.
3. *Citations*: whether each claim's cited evidence exists and the claim is worded like it.

| system | runs | mean time | mean words | sentences no source backs | figures/names in no source | per 100 words |
|---|---|---|---|---|---|---|
| A: model alone | 10 | 28 s | 119 | 57 of 58 (98%) | 10 of 19 (53%) | 0.84 |
| B: model + all sources | 10 | 55 s | 136 | 51 of 59 (86%) | 7 of 67 (10%) | 0.52 |
| PIPELINE | 10 | 223 s | 294 | 78 of 136 (57%) | 4 of 99 (4%) | 0.14 |

The pipeline produced 45 claims over the ten cases; all 45 cite evidence that exists, all 45 are worded like it, and the verifier
marked all 45 supported. That last row is **not** evidence of quality: a claim is dropped unless it is grounded, so it holds by
construction. What it shows is that the citations are real, not that the claims are right.

**What this shows:**

- **Answering from memory is the risky part.** The model alone stated 10 specifics no source contains in 19 (53%), and on the
  thinnest case (Erfurt, 4 sources) 4 of 5. Most of that gain comes from simply giving the model the sources: B is at 10%.
- **The pipeline is lower again, but only just, and the counts are small.** 4 of 99 against 7 of 67 is a few items in ten answers
  from a single run each; it is not a demonstrated difference between B and the pipeline. The larger, more solid difference is on
  the sentence check (57% against 86%), though that is the measure the pipeline is built to pass.
- **It admits what it lacks, by design.** 10 of 10 pipeline runs carried limitations. In its own words the pipeline said so 2 of 10
  times, B 1 of 10 and A 0 of 10, so most of the 10 of 10 is the system attaching the list, not the model choosing to. That is a
  real behavior of the product (the list is always shown) but it is not the same thing as the model hedging.

**What it costs:** the pipeline took about 8 times as long as A and 4 times as long as B, and wrote answers more than twice as long,
which gives its numbers more room to be right or wrong. Per 100 words (last column) the ordering is the same.

**A metric bug, and why both sets of numbers are here.** The first scoring gave the pipeline 25 of 104 specifics in no source
(24%, 0.85 per 100 words), which would have made it no better than A. Reading the examples showed most were the metric's fault:
its name pattern joined the end of one line to the start of the next ("Harvard Square" and "Recent bike theft" became a name),
and it ignored what the system had legitimately been told about a source (a Reddit post's date, a Wikipedia license line). Both
were fixed and all 30 saved answers were re-scored with no new model calls (`python -m evaluation.answer_quality rescore`); the
baselines' numbers did not change. This was a change made after seeing the results, so it is stated here rather than left out, and
a regression test covers the line-break case. Counting provenance as known is fair to the pipeline, which is given it; B's prompt
had titles and text but not publisher or date.

**What this does not show, plainly:**

- **Nothing here measures whether an answer is right or useful.** These are proxies for "stays with its sources". Only a person
  reading the answers can judge correctness, and that has not been done. Answer text is saved locally in `evaluation/runs/` for anyone who wants to.
- **Ten cases and one run each.** The model is not deterministic, so a second run would differ. No confidence intervals are claimed.
- **Frozen, free sources only.** The pipeline was run without its live search, its follow-up research loop, its Reddit and forum
  searches and its translation, because a frozen set has nothing new to fetch. So this measures reading and answering, not
  searching. The sources are English (Wikipedia, English news headlines, mostly English Reddit): the non-English places test thin
  English coverage, not translation. News items are headlines only.
- **The sentence check is strict.** A sentence must be covered by one source, so a fair summary that combines two sources
  fails it. That is why even the cited answers (B) score 86%, and why the pipeline's 57% still means over half its sentences are
  not single-source-backed. (The pipeline's own overview check looks only at its summary and recommendation; this measure looks at
  everything it shows.)
- **Not compared: a paid search, or a paid model.** Nothing here says how the pipeline compares with a hosted assistant.

**To rerun:** `collect` (networked, ten to fifteen minutes, free), `run` (about an hour on this machine's local model), `report`.
A failed run is retried on the next `run`, and a finished one is kept, so an interrupted evaluation resumes.

## What's still needed before claiming more

Baseline A and claim-level measures now exist, in a limited setting (the section above: a local model, frozen free sources, ten
cases, one run each, proxies for staying with the sources). Still missing: a person judging whether the answers are *right*;
the pipeline's live search, follow-up loop and translation in the comparison (they need search credits, or a fixture of them);
repeat runs to show the spread; and any comparison with a hosted model. Until then the honest claim is: *the orchestration layer
improves topic coverage and adds relevance scoring at a real latency cost, and answers given sources state far fewer specifics
found in no source than the model alone (about 10% and 4% against 53%), with the pipeline's advantage over the plain
source-stuffing baseline small and not shown to be reliable at this sample size.*
