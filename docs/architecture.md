# Architecture

## Why one agent, not several

The hard problem here is adaptive retrieval and evidence-grounded reasoning, not
orchestration between specialized agents. A `LocationResearchAgent` calls into a set of
provider-independent tools and pipeline stages; there is no `NewsAgent` or `ReviewAgent`.
If a later milestone's evaluation shows a stage genuinely benefits from being run as an
independent agent (e.g. because it needs its own multi-step tool loop), that's the point
to reconsider — not before.

## Layers

```
app/models/       Pydantic schemas shared by every layer (Location, Evidence, Claim,
                   ResearchPlan/Topic, ResearchTraceStep, ResearchResponse)
app/core/         config (AgentConfig — loop/budget limits) + LLMService interface
app/tools/        LocationResolverTool, WebSearchTool, PageRetrievalTool
app/planning/     topic taxonomy + ResearchPlanner
app/retrieval/    EvidenceRetriever (keyword, semantic, hybrid)
app/evidence/     EvidenceRepository (in-memory, SQLite) + evidence enrichment (quality/recency)
app/synthesis/    ClaimExtractor + Synthesizer
app/verification/ ClaimVerifier + contradiction detection
app/agents/       LocationResearchAgent (orchestration) + factory wiring
app/api/          FastAPI route
```

Each layer that could swap in a real (paid, networked, LLM-backed, or just heavier) implementation
is an abstract interface with a free, deterministic default alongside it:

| Interface | Free / deterministic default | Alternative implementation |
|---|---|---|
| `LocationResolverTool` | `FixtureLocationResolver` (alias lookup in `fixtures/locations.json`) | Geocoding API (not scheduled — low priority; alias lookup covers the demo locations) |
| `WebSearchTool` | `FixtureWebSearchTool` (reads `fixtures/sources/<slug>/<topic>.json`) | `TavilyWebSearchTool` — real search via the Tavily API (opt-in via `TAVILY_API_KEY`) |
| `PageRetrievalTool` | `FixturePageRetrievalTool` (full-text lookup from the same fixtures) | `TavilyPageRetrievalTool` — reads full text Tavily already returned during search |
| `ResearchPlanner` | `KeywordResearchPlanner` (rule-based keyword → topic mapping) | `LLMResearchPlanner` — chooses from the fixed topic taxonomy via the LLM (opt-in via `ANTHROPIC_API_KEY`) |
| `EvidenceRetriever` | `KeywordEvidenceRetriever` (lexical term-overlap scoring) | `HybridEvidenceRetriever` (keyword + `SemanticEvidenceRetriever`, local `sentence-transformers`; auto-enabled if installed, opt-out via `DISABLE_SEMANTIC_RETRIEVAL=1`) |
| `EvidenceRepository` | `InMemoryEvidenceRepository` (per-run, not persisted) | `SQLiteEvidenceRepository` — durable, per-run-scoped local file, the actual default in `build_default_agent()` |
| `ClaimExtractor` | `FixtureClaimExtractor` (reads a pre-annotated `claim_text` per fixture doc) | `LLMClaimExtractor` — extracts from real evidence text, grounding-checked (opt-in via `ANTHROPIC_API_KEY`) |
| `ClaimVerifier` | `EvidenceBasedClaimVerifier` — relevance/recency checks, always; a second deterministic pass flags same-topic contradictions via a coarse antonym heuristic (never LLM-backed) | — (no alternative implementation; see "Provenance and honesty" below for why) |
| `Synthesizer` | `TemplateSynthesizer` (renders verified claims into prose via templates) | `LLMSynthesizer` — drafts prose from verified claims only, rejects absolute language (opt-in via `ANTHROPIC_API_KEY`) |
| `LLMService` | `FakeLLMService` (deterministic; used only in tests) | `AnthropicLLMService` (opt-in via `ANTHROPIC_API_KEY`) |

`app/agents/factory.py` is the one place that wires concrete implementations together;
everything else — including `LocationResearchAgent` itself — depends only on the interfaces,
via constructor injection. `build_default_agent()` auto-detects `ANTHROPIC_API_KEY`,
`TAVILY_API_KEY`, and whether `sentence-transformers` is installed, independently of each other,
and picks components accordingly with no other code changing either way. Every LLM-backed
implementation also falls back to its deterministic counterpart on failure (bad JSON, API error,
a rejected/ungrounded response) — see `docs/research-workflow.md`'s "LLM integration" section
for exactly what is and isn't trusted to the LLM, and its "Live search" section for what changes
once real evidence is in play (notably: real evidence needs `LLMClaimExtractor` to become
claims — `FixtureClaimExtractor` can't read real page text).

## Why hybrid retrieval, not just semantic

`KeywordEvidenceRetriever`'s real, documented limitation was that a query for "commute options"
won't match a passage that only says "getting to campus" — no shared literal tokens.
`SemanticEvidenceRetriever` (local `sentence-transformers` embeddings, no API key) fixes exactly
that gap; `tests/test_semantic_retriever.py` demonstrates it on that literal example.
`HybridEvidenceRetriever` blends both scores rather than replacing keyword with semantic
outright, because semantic similarity can also drift toward loosely-related passages that share
a topic but not real relevance — neither method strictly dominates the other. The blend ratio
(`keyword_weight`, default 0.5) is not tuned against a labeled benchmark; that tuning is exactly
what would need to happen before trusting the ratio itself, as opposed to the general approach.

## Provenance and honesty by construction

Every `Evidence` object carries its source URL, publisher, source type, retrieval and
publication timestamps, and the exact passage used — the schema makes it structurally
impossible to state a claim without a traceable source. `Claim.status` is set only by
`ClaimVerifier`, never by whatever proposed the claim text (rule-based or LLM), so "a claim was
extracted" and "a claim is supported" can never be conflated. This holds regardless of whether
an LLM is in the loop — `ClaimVerifier` is never LLM-backed and never moves in the pipeline
order (see `docs/research-workflow.md`). Its contradiction check is a real but deliberately
coarse keyword-antonym heuristic (`app/verification/contradiction.py`), documented as exactly
that rather than oversold as full natural-language understanding. Remaining known gaps
(fixture-only data unless live search is enabled, no real geocoding) are surfaced in every
response's `limitations` field rather than hidden.

## Milestone status

All eight milestones from the original project plan are implemented; what's opt-in vs. free by
default is summarized in the interface table above.

- **Milestone 1:** fixture-backed, fully deterministic pipeline. No API key, no network.
- **Milestone 2:** LLM-backed planning, claim extraction, and synthesis — opt-in via
  `ANTHROPIC_API_KEY`, each falling back to its Milestone 1 counterpart on failure.
- **Milestone 3:** live web search + page retrieval via Tavily — opt-in via `TAVILY_API_KEY`,
  independently of the LLM key. Real evidence collected this way needs `LLMClaimExtractor`
  (i.e. both keys set) to actually become claims — see `docs/research-workflow.md`.
- **Milestone 4:** hybrid (keyword + local-embedding semantic) retrieval — auto-enabled if
  `sentence-transformers` is installed, opt-out via `DISABLE_SEMANTIC_RETRIEVAL=1`.
- **Milestone 5:** `SQLiteEvidenceRepository` — durable, per-run-scoped local storage, the
  actual default (`InMemoryEvidenceRepository` still exists and is used directly in unit tests).
- **Milestone 6:** cross-source contradiction detection in `ClaimVerifier` — a coarse,
  deterministic antonym heuristic, not full NLU (see above).
- **Milestone 7:** the React + TypeScript frontend (`frontend/`) with a Leaflet/OpenStreetMap
  map — a thin client that renders exactly what the API returns; see `frontend/README.md`.
- **Milestone 8:** the evaluation benchmark was actually run (Baseline B vs. the proposed
  system's orchestration, live search, no LLM key available) and results — including where the
  proposed system did *not* win — are reported in `docs/evaluation.md`, not just planned.
  Baseline A and claim-level metrics remain unmeasured pending an `ANTHROPIC_API_KEY`.
