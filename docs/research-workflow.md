# Research Workflow (Milestone 1)

```
INPUT (raw location string, question)
  -> LOCATION RESOLUTION        FixtureLocationResolver.resolve()
  -> QUESTION UNDERSTANDING     folded into planning: intent detection
  -> RESEARCH PLANNING          KeywordResearchPlanner.plan() -> ResearchPlan
  -> per topic, bounded by AgentConfig.max_tool_calls:
       TOOL SELECTION           log which tool + queries are used
       RETRIEVAL                WebSearchTool.search() -> KeywordEvidenceRetriever.score()
       EVIDENCE PROCESSING      filter by relevance threshold, cap per topic,
                                PageRetrievalTool.retrieve_full_text(), enrich_evidence()
  -> COVERAGE CHECK             which planned topics ended up with zero evidence
  -> CLAIM EXTRACTION           FixtureClaimExtractor.extract()
  -> CLAIM VERIFICATION         EvidenceBasedClaimVerifier.verify()
  -> SYNTHESIS                  TemplateSynthesizer.synthesize()
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

## Why verification runs before synthesis in this milestone

The project's general lifecycle lists synthesis before claim verification, which fits an
LLM-based synthesizer that drafts an answer and then has that draft checked. Milestone 1's
`TemplateSynthesizer` is extractive, not generative: it renders already-verified claims into
prose rather than drafting new text. There is nothing to check after the fact, so verification
runs first and its output (`ClaimStatus`, per-claim limitations) directly shapes the wording
used ("supported by N source(s)" vs. "not confirmed by sufficient evidence"). A Milestone 2
LLM-backed synthesizer would restore the draft-then-verify order, since at that point there
would be a generated draft worth checking.

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

Because Milestone 1's fixtures are static, there is no broadened second search that would
surface different results if a topic comes back empty — the loop still records this
explicitly (`ADDITIONAL_RESEARCH` trace stage, `"nothing further to fetch in this run"`)
rather than pretending a retry happened. This becomes meaningful once Milestone 2 adds a real
search tool where a broadened query can plausibly return something new.

## Claim extraction: an honest placeholder

`FixtureClaimExtractor` does not perform free-text claim extraction. Each fixture document is
pre-annotated with the claim it was written to support (`metadata["claim_text"]`), and the
extractor groups evidence that shares a claim within a topic — which is how two independent
fixture sources end up corroborating a single claim in `tests/test_agent_end_to_end.py`. This
stands in for what an LLM-based extractor would produce from real page text, and is called out
explicitly in code and in `backend/README.md` so it's never mistaken for real NLP.
