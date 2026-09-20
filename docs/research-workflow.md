# Research Workflow

```
INPUT (raw location string, question)
  -> LOCATION RESOLUTION        Google Places, then OpenStreetMap Nominatim
  -> QUESTION UNDERSTANDING     folded into planning: intent detection
  -> RESEARCH PLANNING          ResearchPlanner.plan() -> ResearchPlan
                                 (KeywordResearchPlanner, or LLMResearchPlanner if
                                  OLLAMA_ENABLED is set — see "LLM integration" below)
  -> per topic, bounded by AgentConfig.max_tool_calls:
       TOOL SELECTION           log which tool + queries are used
       RETRIEVAL                WebSearchTool.search() -> KeywordEvidenceRetriever.score()
       EVIDENCE PROCESSING      filter by relevance threshold, cap per topic,
                                PageRetrievalTool.retrieve_full_text(), enrich_evidence()
  -> COVERAGE CHECK             which planned topics ended up with zero evidence
  -> CLAIM EXTRACTION           ClaimExtractor.extract() (LLM-based; none without a model)
  -> CLAIM VERIFICATION         EvidenceBasedClaimVerifier.verify()   <- always deterministic
  -> SYNTHESIS                  Synthesizer.synthesize() (Template- or LLM-based)
  -> FINAL RESPONSE             ResearchResponse, including the full research_trace
```

Every stage above appends a `ResearchTraceStep` to the response — this is what "the user can
understand what the agent did" means concretely in this milestone.

## Adaptive topic selection

`KeywordResearchPlanner` (`app/planning/planner.py`) selects topics in three passes, in
priority order:

1. **Explicit mention** — if the question's own text matches a topic's keywords (e.g. it says
   "nightlife"), that topic is included at `HIGH` priority regardless of anything else.
2. **Persona bundle** — if the question matches a known persona (currently just
   `college_student`, triggered by phrases like "college student" or "undergrad"), that
   persona's default topic bundle (`housing`, `transportation`, `safety`,
   `student_amenities`, `cost_of_living`) is added at `MEDIUM` priority, without overriding
   anything already set to `HIGH`.
3. **Fallback** — only if neither of the above matched anything, a small generic bundle
   (`housing`, `transportation`, `safety`) is used at `LOW` priority, so the agent never
   researches nothing.

This is what makes "a nightlife question should not trigger extensive housing research"
concretely true: pass 1 selects only `nightlife`; passes 2 and 3 never run because
`topic_priority` is already non-empty. See `tests/test_planner.py`.

## LLM integration (Milestone 2) — where the LLM is trusted, and where it isn't

Setting `OLLAMA_ENABLED` swaps three components for LLM-backed versions
(`app/agents/factory.py` auto-detects this):

- `LLMResearchPlanner` — chooses which topics are relevant using real language understanding
  (e.g. "Is it easy to get around without a car?" implies `transportation` with no literal
  keyword match), but can only select from the fixed topic taxonomy in `app/planning/topics.py`
  — it cannot invent a topic, its queries, or its completion criteria.
- `LLMClaimExtractor` — extracts real claims from evidence passages instead of relying on
  pre-written claims. Every `supporting_evidence_ids` it returns is checked against
  the evidence actually given to it; ids that don't correspond to real evidence are dropped, and
  a claim left with none is dropped entirely (`app/synthesis/llm_claim_extractor.py`).
- `LLMSynthesizer` — drafts the summary/recommendation prose, but only from claims that have
  already been verified, and its recommendation is rejected (triggering a template-based
  fallback) if it uses disallowed absolute language like "guaranteed."

**Claim verification never becomes an LLM call, and it never moves.** It stays a fixed,
deterministic gate between extraction and synthesis regardless of which components are
LLM-backed: `EvidenceBasedClaimVerifier` is the same class either way. This is why the pipeline
order above is extract → verify → synthesize, not the "generate an answer, then check it"
pattern you might expect from an LLM-heavy system — letting an LLM draft a full narrative answer
and checking it afterwards would mean trusting the LLM not to introduce anything ungrounded in
the first place, which is exactly the failure mode `ClaimVerifier` exists to prevent. Likewise,
`deterministic_limitations()` (`app/synthesis/synthesizer.py`) computes coverage gaps and the
standing contradiction-detection caveat in code for both synthesizers, so an LLM that omits an
inconvenient limitation cannot make it disappear from the response.

Every LLM-backed component falls back to its rule-based or empty counterpart
on any failure — a malformed JSON response, a rejected recommendation, a network error, no valid
topics/claims — and records why in the response's `limitations`, rather than crashing the run
or silently degrading without saying so. See `tests/test_llm_planner.py`,
`tests/test_llm_claim_extractor.py`, and `tests/test_llm_synthesizer.py`, all of which exercise
this against a scripted fake `LLMService` rather than the real API.

## Live search (Milestone 3) — and why it needs the LLM key to be useful

Setting `TAVILY_API_KEY` swaps `WebSearchTool`/`PageRetrievalTool` for `TavilyWebSearchTool`/
`TavilyPageRetrievalTool` (`app/tools/tavily_tools.py`), independently of `OLLAMA_ENABLED`.
Tavily returns full page text (`include_raw_content=True`) in the same call as the search
results, so the page-retrieval tool just reads from a cache the search tool already populated
rather than making a second real HTTP request per source.

Real results don't arrive labeled with a clean `source_type` — `_classify_source_type()` is a
coarse, honest heuristic keyed on domain (`.gov` → `local_government`, `reddit.com` →
`community_forum`, etc.) that defaults to `SourceType.OTHER` rather than guessing wrong.

**The important interaction: live search alone produces evidence without claims.**
Reading a claim out of a real page needs a model, so with `TAVILY_API_KEY` set but
not `OLLAMA_ENABLED`, a run collects real evidence that never becomes a claim
(`UnavailableClaimExtractor` says so). This is not a
bug being papered over: `deterministic_limitations()` reports it explicitly as *"Evidence was
found for planned topic 'x' but no claims could be extracted from it"* — distinct from *"No
evidence was found"* — so real, gathered evidence with no claim is never confused with a
genuine coverage gap. Confirmed against the live API: asking about Harvard Square nightlife
with only `TAVILY_API_KEY` set returns real evidence from Yelp, Reddit, and a local blog, zero
claims, and exactly that limitation message. Setting both keys is what makes live search
actually produce claims, via `LLMClaimExtractor`.

## Retrieval: why lexical first

`KeywordEvidenceRetriever` scores each candidate by term overlap against the topic's search
queries. It is deterministic and requires no embedding model, which is why it's what runs
today — but it is a real limitation, not a stylistic choice: a query for "commute options"
will not match a passage that only says "getting to campus," because they share no literal
tokens. `docs/evaluation.md` describes how that specific failure mode gets measured before a
semantic retriever is added on top.

## The research loop's bound

`AgentConfig.max_tool_calls` (default 30) counts every external tool call — each topic's
search plus each accepted candidate's full-text fetch — so the loop is guaranteed to
terminate. When the budget runs out mid-topic, that topic is skipped and a
`"Research budget exhausted..."` limitation is recorded rather than silently truncating
results. `AgentConfig.max_evidence_per_topic` and `min_relevance_score` bound how much
evidence a single topic can contribute and how weak a match can still be accepted.

## The decide-and-act loop

The first pass is fixed: plan topics, search each once, score, keep what clears the relevance bar.
What happens next is a decision. `app/agents/reflection.py` defines a `Reflector` that receives the
question, what evidence exists per planned topic, and the queries already tried, and returns either
"enough" or up to `max_actions_per_round` actions from a fixed menu:

- `web_search` — search again with a new query. The first pass used fixed per-topic templates
  that never contain the user's question; the follow-up is built from it.
- `wikimedia` — Wikipedia articles near the pin and the Wikivoyage guide for the town
  (`app/tools/wiki_tool.py`), for visiting/nearby questions or when web search found nothing.

With an LLM enabled, `LLMReflector` makes the choice; anything it proposes outside the menu, for an
unknown topic, or repeating a tried query is discarded, and if the call fails or returns garbage
`RuleBasedReflector` decides instead and the limitation says so. The *agent* executes the actions,
so the model can pick and phrase but cannot run anything itself. Results pass through the same
relevance filter and budget as the first pass. The loop runs at most `max_research_rounds` (default
2) times and stops early when the reflector says enough or `max_tool_calls` is spent, so it always
terminates. Every decision is a trace step (`ADDITIONAL_RESEARCH`), including "enough".

The loop is only wired when live search is on: with no search configured there is nothing to search again.
documents. Without it the run is the single fixed pass.

## Places outside the English-speaking world

Before the first search, `LocaleResolver` reverse-geocodes the pin to find the country and looks up the
country's main written language (only languages the free translator can read back are listed). For
such a place the plan gains one query per top topic in that language, built around the place's
native-script name (`ResearchTopic.local_queries`). `TavilyWebSearchTool` runs it alongside the English
query and merges the results by URL; the retrievers still score only the English queries, because
they score English text. Pages are accepted on the native name as well as the English one. For an
English-speaking place, or one whose language can't be translated, nothing changes and the trace says
why (`RESEARCH_PLANNING`). Any failure in the lookup is a limitation, never an error.

## Claim extraction without an LLM

Without a model there is no claim extraction: `UnavailableClaimExtractor` returns no claims and adds
a note that a model is needed, and the response still lists the sources it found. There used to be a
`FixtureClaimExtractor` that returned pre-written claims attached to invented fixture documents, and
`LLMClaimExtractor` fell back to it on failure. It was removed from the product because it let
invented statements pass as research; it survives only in `tests/fixture_tools.py`, where it drives
the end-to-end tests. When `LLMClaimExtractor` fails it now produces no claims and says so.

