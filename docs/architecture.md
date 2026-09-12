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
app/retrieval/    EvidenceRetriever
app/evidence/     EvidenceRepository + evidence enrichment (quality/recency scoring)
app/synthesis/    ClaimExtractor + Synthesizer
app/verification/ ClaimVerifier
app/agents/       LocationResearchAgent (orchestration) + factory wiring
app/api/          FastAPI route
```

Each layer that could later swap in a real (paid, networked, LLM-backed) implementation is
an abstract interface with a concrete Milestone 1 implementation next to it:

| Interface | Milestone 1 implementation | What replaces it later |
|---|---|---|
| `LocationResolverTool` | `FixtureLocationResolver` (alias lookup in `fixtures/locations.json`) | Geocoding API |
| `WebSearchTool` | `FixtureWebSearchTool` (reads `fixtures/sources/<slug>/<topic>.json`) | Real search API (e.g. Tavily, Bing) |
| `PageRetrievalTool` | `FixturePageRetrievalTool` (full-text lookup from the same fixtures) | Real page fetch + extraction |
| `ResearchPlanner` | `KeywordResearchPlanner` (rule-based keyword → topic mapping) | LLM-based planner |
| `EvidenceRetriever` | `KeywordEvidenceRetriever` (lexical term-overlap scoring) | + semantic retrieval, reranking |
| `EvidenceRepository` | `InMemoryEvidenceRepository` (per-run, not persisted) | Postgres/pgvector-backed |
| `ClaimExtractor` | `FixtureClaimExtractor` (reads a pre-annotated `claim_text` per fixture doc) | LLM-based extraction from free text |
| `ClaimVerifier` | `EvidenceBasedClaimVerifier` (checks relevance + recency; no contradiction detection yet) | + cross-source contradiction detection |
| `Synthesizer` | `TemplateSynthesizer` (renders verified claims into prose via templates) | LLM-based synthesis |
| `LLMService` | `FakeLLMService` (deterministic; unused by the M1 pipeline) | Anthropic-backed implementation |

`app/agents/factory.py` is the one place that wires concrete implementations together;
everything else — including `LocationResearchAgent` itself — depends only on the interfaces,
via constructor injection. This is what lets the whole pipeline run and be unit-tested with
zero network access and no API key, and it's the seam a later milestone uses to go live one
component at a time (e.g. plug in a real search tool while everything else stays fixture-backed).

## Why not a vector database yet

Milestone 1's retrieval is lexical term-overlap (`KeywordEvidenceRetriever`), not because
semantic retrieval isn't valuable, but because a vector database only earns its place once
there's a retrieval-quality problem it demonstrably fixes — e.g. a query and a passage that
mean the same thing but share no literal tokens. `docs/evaluation.md` describes how that gap
will actually be measured before pgvector (or similar) gets added, rather than adding it
because a "real" system is expected to have one.

## Provenance and honesty by construction

Every `Evidence` object carries its source URL, publisher, source type, retrieval and
publication timestamps, and the exact passage used — the schema makes it structurally
impossible to state a claim without a traceable source. `Claim.status` is set only by
`ClaimVerifier`, never by whatever proposed the claim text, so "a claim was extracted" and
"a claim is supported" can never be conflated. Known gaps (no LLM reasoning yet, no
contradiction detection yet, fixture-only data) are surfaced in every response's
`limitations` field rather than hidden.

## What Milestone 2+ is expected to add

- An LLM-backed `ResearchPlanner` and `Synthesizer` (via `LLMService`), replacing the
  rule-based ones — the interfaces already exist for this.
- Real free-text claim extraction via an LLM, replacing `FixtureClaimExtractor`'s reliance on
  pre-annotated fixture metadata.
- A real `WebSearchTool` (search API) and `PageRetrievalTool` (page fetch + extraction).
- Semantic retrieval and reranking alongside the existing lexical retriever, plus a
  Postgres/pgvector-backed `EvidenceRepository` if evaluation shows the in-memory one is
  insufficient.
- Cross-source contradiction detection in `ClaimVerifier`.
- The React map frontend, once the backend workflow above is stable.
