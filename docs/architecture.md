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
| `LocationResolverTool` | `FixtureLocationResolver` (alias lookup in `fixtures/locations.json`) | `NominatimLocationResolverTool` — real geocoding for any point of interest via free OpenStreetMap Nominatim, wrapped in `FallbackLocationResolver` so the two demo neighborhoods still resolve instantly from fixtures (opt-out via `DISABLE_LIVE_GEOCODING=1`) |
| `WebSearchTool` | `FixtureWebSearchTool` (reads `fixtures/sources/<slug>/<topic>.json`) | `TavilyWebSearchTool` — real search via the Tavily API (opt-in via `TAVILY_API_KEY`) |
| `PageRetrievalTool` | `FixturePageRetrievalTool` (full-text lookup from the same fixtures) | `TavilyPageRetrievalTool` — reads full text Tavily already returned during search |
| `ResearchPlanner` | `KeywordResearchPlanner` (rule-based keyword → topic mapping) | `LLMResearchPlanner` — chooses from the fixed topic taxonomy via the LLM (opt-in via `ANTHROPIC_API_KEY` or `OLLAMA_ENABLED`) |
| `EvidenceRetriever` | `KeywordEvidenceRetriever` (lexical term-overlap scoring) | `HybridEvidenceRetriever` (keyword + `SemanticEvidenceRetriever`, local `sentence-transformers`; auto-enabled if installed, opt-out via `DISABLE_SEMANTIC_RETRIEVAL=1`) |
| `EvidenceRepository` | `InMemoryEvidenceRepository` (per-run, not persisted) | `SQLiteEvidenceRepository` — durable, per-run-scoped local file, the actual default in `build_default_agent()` |
| `ClaimExtractor` | `FixtureClaimExtractor` (reads a pre-annotated `claim_text` per fixture doc) | `LLMClaimExtractor` — extracts from real evidence text (opt-in via `ANTHROPIC_API_KEY` or `OLLAMA_ENABLED`). Grounding is enforced independently of the LLM's self-report: a cited evidence id/topic is checked against the real evidence given, and if that citation doesn't validate, `_best_matching_evidence()` recovers grounding by lexical overlap between the claim's own wording and the real evidence text — a claim is kept only if one of those two checks passes, never on the LLM's say-so alone |
| `ClaimVerifier` | `EvidenceBasedClaimVerifier` — relevance/recency checks, always; a second deterministic pass flags same-topic contradictions via a coarse antonym heuristic (never LLM-backed) | — (no alternative implementation; see "Provenance and honesty" below for why) |
| `Synthesizer` | `TemplateSynthesizer` — renders verified claims into prose via templates; for a topic with evidence but no claim, quotes the single most relevant *and* credible excerpt (blending relevance with a source-type quality score) rather than reporting only a gap | `LLMSynthesizer` — sees both verified claims and the full raw evidence (grouped by topic, labeled by source type/publisher/date), so it can answer the actual question from real evidence even when claim extraction found little; rejects absolute language, including absolute safety claims like "no crime has ever happened here" (opt-in via `ANTHROPIC_API_KEY` or `OLLAMA_ENABLED`) |
| `LLMService` | `FakeLLMService` (deterministic; used only in tests) | `AnthropicLLMService` (opt-in via `ANTHROPIC_API_KEY`, billed) or `OllamaLLMService` (opt-in via `OLLAMA_ENABLED`, free and local; Anthropic takes priority if both are set) |

`app/agents/factory.py` is the one place that wires concrete implementations together;
everything else — including `LocationResearchAgent` itself — depends only on the interfaces,
via constructor injection. `build_default_agent()` auto-detects `ANTHROPIC_API_KEY`/
`OLLAMA_ENABLED`, `TAVILY_API_KEY`, live geocoding, and whether `sentence-transformers` is
installed, independently of each other, and picks components accordingly with no other code
changing either way. Every LLM-backed implementation also falls back to its deterministic
counterpart on failure (bad JSON, API error, a rejected/ungrounded response) — see
`docs/research-workflow.md`'s "LLM integration" section for exactly what is and isn't trusted to
the LLM.

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

All eight milestones from the original project plan are implemented, plus two later additions
(9 and 10, below); what's opt-in vs. free by default is summarized in the interface table above.

- **Milestone 1:** fixture-backed, fully deterministic pipeline. No API key, no network.
- **Milestone 2:** LLM-backed planning, claim extraction, and synthesis — opt-in via
  `ANTHROPIC_API_KEY` or the free local `OLLAMA_ENABLED`, each falling back to its Milestone 1
  counterpart on failure.
- **Milestone 3:** live web search + page retrieval via Tavily — opt-in via `TAVILY_API_KEY`,
  independently of the LLM key.
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
- **Milestone 9:** research isn't limited to a neighborhood — `NominatimLocationResolverTool` /
  `NominatimPlaceSearchTool` resolve and search for any real point of interest (a specific
  business, address, building) via free OpenStreetMap Nominatim, opt-out via
  `DISABLE_LIVE_GEOCODING=1`. Picking one exact POI from live search passes the already-resolved
  `Location` straight into the agent (`LocationResearchAgent.run()` accepts `str | Location`),
  skipping re-resolution so a same-named place nearby can't be silently substituted.
- **Milestone 10:** the independent, region-scoped live feed (`TavilyLiveFeedTool` /
  `GET /api/live-feed`) and a rework of claim extraction and synthesis so a real, useful body of
  evidence doesn't collapse into "insufficient evidence":
  - The live feed reports on the broader area (city/region), not the specific selected place —
    querying and filtering are anchored on the region, with a title-or-repeated-mention check to
    reject a passing name-check of the region in unrelated content.
  - `LLMClaimExtractor` recovers grounding deterministically (`_best_matching_evidence`, lexical
    overlap against real evidence text) when a model cites a source name or an invented topic
    label instead of the literal evidence id/topic it was given, rather than dropping every claim
    a weaker model produces.
  - `Synthesizer.synthesize()` now sees the full evidence set, not only already-extracted claims,
    and returns a structured `SynthesisResult` (`summary`, `key_findings`, `details`,
    `recommendation`) — both `TemplateSynthesizer` and `LLMSynthesizer` can produce a real,
    question-answering Overview even when claim extraction found little or nothing, instead of
    defaulting to "insufficient evidence" purely because one precisely-formatted extraction step
    didn't succeed.
