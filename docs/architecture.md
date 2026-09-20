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

Each layer that could swap in a real (networked, LLM-backed, or just heavier) implementation is an
abstract interface. Where a service isn't configured the default returns nothing and says so; it is
never a stand-in that invents data:

| Interface | Default when nothing is configured | Real implementation |
|---|---|---|
| `LocationResolverTool` | `UnconfiguredLocationResolver` (says geocoding is off) | `GooglePlacesLocationResolver` when `GOOGLE_PLACES_API_KEY` is set, then `NominatimLocationResolverTool` (free OpenStreetMap; opt-out via `DISABLE_LIVE_GEOCODING=1`), chained by `FallbackLocationResolver` (`build_location_resolver`) |
| `WebSearchTool` | `UnconfiguredWebSearchTool` (returns nothing; the response says search isn't configured) | `TavilyWebSearchTool` — real search via the Tavily API (opt-in via `TAVILY_API_KEY`) |
| `PageRetrievalTool` | `UnconfiguredPageRetrievalTool` (returns nothing) | `TavilyPageRetrievalTool` — reads full text Tavily already returned during search |
| `ResearchPlanner` | `KeywordResearchPlanner` (rule-based keyword → topic mapping) | `LLMResearchPlanner` — chooses from the fixed topic taxonomy via the LLM (opt-in via `OLLAMA_ENABLED`) |
| `EvidenceRetriever` | `KeywordEvidenceRetriever` (lexical term-overlap scoring) | `HybridEvidenceRetriever` (keyword + `SemanticEvidenceRetriever`, local `sentence-transformers`; auto-enabled if installed, opt-out via `DISABLE_SEMANTIC_RETRIEVAL=1`) |
| `EvidenceRepository` | `InMemoryEvidenceRepository` (per-run, not persisted) | `SQLiteEvidenceRepository` — durable, per-run-scoped local file, the actual default in `build_default_agent()` |
| `ClaimExtractor` | `UnavailableClaimExtractor` (no claims; says a model is needed) | `LLMClaimExtractor` — extracts from real evidence text (opt-in via `OLLAMA_ENABLED`). Grounding is enforced independently of the LLM's self-report: a cited evidence id/topic is checked against the real evidence given, and if that citation doesn't validate, `_best_matching_evidence()` recovers grounding by lexical overlap between the claim's own wording and the real evidence text — a claim is kept only if one of those two checks passes, never on the LLM's say-so alone |
| `ClaimVerifier` | `EvidenceBasedClaimVerifier` — relevance/recency checks, always; a second deterministic pass flags same-topic contradictions via a coarse antonym heuristic (never LLM-backed) | — (no alternative implementation; see "Provenance and honesty" below for why) |
| `Synthesizer` | `TemplateSynthesizer` — renders verified claims into prose via templates; for a topic with evidence but no claim, quotes the single most relevant *and* credible excerpt (blending relevance with a source-type quality score) rather than reporting only a gap | `LLMSynthesizer` — sees both verified claims and the full raw evidence (grouped by topic, labeled by source type/publisher/date), so it can answer the actual question from real evidence even when claim extraction found little; rejects absolute language, including absolute safety claims like "no crime has ever happened here" (opt-in via `OLLAMA_ENABLED`) |
| `LLMService` | — (none: without a model the LLM-backed components are simply not used) | `OllamaLLMService` (opt-in via `OLLAMA_ENABLED`, free and local). It is the only real implementation; the interface stays provider-independent, so another can be added without touching the pipeline |

`app/agents/factory.py` is the one place that wires concrete implementations together;
everything else — including `LocationResearchAgent` itself — depends only on the interfaces,
via constructor injection. `build_default_agent()` auto-detects `OLLAMA_ENABLED`, `TAVILY_API_KEY`, live geocoding, and whether `sentence-transformers` is
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
(no evidence at all unless live search is configured, no claims without a model) are surfaced in every
response's `limitations` field rather than hidden.

## Milestone status

All eight milestones from the original project plan are implemented, plus later additions
(9 onward, below); what's opt-in vs. free by default is summarized in the interface table above.

- **Milestone 1:** the deterministic pipeline, first built and tested against invented fixture
  documents for two neighborhoods. Those fixtures have since been moved out of the product (see the
  last milestone below).
- **Milestone 2:** LLM-backed planning, claim extraction, and synthesis — opt-in via the free
  local `OLLAMA_ENABLED`, falling back to its Milestone 1 counterpart on failure.
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
  system's orchestration, live search, without the LLM-backed components) and results — including where the
  proposed system did *not* win — are reported in `docs/evaluation.md`, not just planned.
  Baseline A and claim-level metrics remain unmeasured.
- **Milestone 9:** research isn't limited to a neighborhood — `NominatimLocationResolverTool` /
  `NominatimPlaceSearchTool` resolve and search for any real point of interest (a specific
  business, address, building) via free OpenStreetMap Nominatim, opt-out via
  `DISABLE_LIVE_GEOCODING=1`. A free-text query is tried as-is and then progressively broadened
  by dropping leading segments, because OSM knows addresses far better than business names —
  "Venezuela, 20 Ericsson St, Boston, MA 02122" returns nothing while the address alone resolves
  exactly, and the name the user typed is kept for display. Naming a US state also constrains the
  search to that country, without which a business name that is also a country name hijacks the
  geocode entirely ("Venezuela, Boston, MA" resolved to a street in Venezuela). Picking one exact POI from live search passes the already-resolved
  `Location` straight into the agent (`LocationResearchAgent.run()` accepts `str | Location`),
  skipping re-resolution so a same-named place nearby can't be silently substituted.
- **Milestone 10:** the independent, region-scoped live feed (`TavilyLiveFeedTool` /
  `GET /api/live-feed`) and a rework of claim extraction and synthesis so a real, useful body of
  evidence doesn't collapse into "insufficient evidence":
  - The live feed reports on the broader area (city/region), not the specific selected place —
    querying and filtering are anchored on the region. It searches Tavily's *news* topic across
    several complementary facets and merges them: the general topic returned no publication date
    at all for any result and mostly evergreen landing pages, so items are required to carry a
    real publication timestamp, which doubles as the quality filter. Locality is checked against
    the publisher/URL as well as the text, accepting a hyper-local outlet outright while
    requiring everything else to name the state too (a Cambridge, MA query otherwise surfaced a
    Cambridge, *New York* police report).
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

- **Milestone 11:** places in any language. `Translator` / `ArgosTranslator`
  (`app/tools/translation.py`) machine-translates foreign-language evidence to English locally
  (Argos Translate, free, no key; language packs download on first use), *before* the relevance
  filters, since a Japanese page never spells the place the way an English query does. The
  original title and text are kept in `Evidence.metadata` and the UI labels every translated item;
  text that can't be translated is flagged, never dropped or faked. Nominatim is asked for English
  names, a missing prefecture/state is recovered from the display name, and the minimum-length
  filter counts CJK characters at their real information weight (a plain `len()` discarded short
  but complete Japanese passages).
- **Milestone 12:** a specific business is researched as a business, and gets real map and
  ratings data. `Location.is_business` (from OpenStreetMap's `category`) switches the plan to
  business-specific queries, and `_mentions_business` / `_mentions_place_context` require a page
  to name the business's distinguishing words *and* the right city, with no soft fallback. Three
  data sources sit beside web search, each independent of the LLM: `OverpassNearbyTool` ("around
  this pin" from OpenStreetMap map data, with a mirror fallback and a cache), `GooglePlacesTool`
  (rating, hours, Google's review summary as cited evidence; optional, needs
  `GOOGLE_PLACES_API_KEY` and billing), and `best_excerpt` (`app/synthesis/excerpt.py`), which
  gives the model the passage of a page that matches the question rather than its first few hundred
  characters, usually navigation. Checked live against Google, `reviews` came back absent for a
  busy place on both endpoints while `reviewSummary` came back fine, so the summary is kept and
  labeled as Google's own AI text.
  A user-reported miss (a restaurant in Kurume pasted as a plus code) showed the deeper problem:
  the place was being *found* by OpenStreetMap, which lacks the business and can't read plus codes,
  so it was never flagged as a business and Google was never asked. `GooglePlacesTool.search_places`
  and `GooglePlacesLocationResolver` now resolve places first when the key is set, with OpenStreetMap
  as fallback; the same question then returned Google's 3.9 stars from 384 reviews plus a Tabelog page.
- **Milestone 13:** the dependency and pipeline cleanup. The Anthropic provider and the Firecrawl
  integration were removed: neither was exercised (no key was ever used for the first; the second
  fired on 0 of 14 measured pages and returned neither cleaner text nor dates), and a billed model
  API doesn't fit a project that is meant to stay free. What remains is one LLM provider (Ollama)
  behind the provider-independent `LLMService` interface, GitHub Actions for CI, security and
  release, and Dependabot. The default model moved from `llama3.2:3b` to `qwen3:30b` (a
  mixture-of-experts model, ~3B active parameters) with thinking mode off and Ollama's integrated-GPU
  backend on: measured at 192 s for a business question and 259 s for a neighbourhood question,
  against 15+ minutes for the same model on CPU only. `backend/README.md` has the full timing table
  and how each number was obtained.
- **Milestone 14:** an audit of whether the agent and the RAG were doing what the project claims found
  four gaps, all now addressed. (1) *The agent didn't decide anything*: a fixed sequence; the
  `ADDITIONAL_RESEARCH` trace stage only logged. It now has a bounded reflect-then-act loop over two
  tools (`app/agents/reflection.py`; see `docs/research-workflow.md`). (2) *Retrieval never saw the
  question*: the search used one fixed template query per topic; follow-up queries are now built from
  the question. (3) *"Supported" meant less than it sounded*: a model-written claim that cited a real
  evidence id was marked supported without anyone checking its wording, so a real citation could
  vouch for an invented sentence. The verifier now also requires the claim's content words (at least
  half) and every figure in it to appear in the sources it cites (`app/verification/support.py`).
  (4) *The overview was unchecked prose*: sentences that no single source backs are now listed in the
  limitations as the model's own inference. Both checks are lexical, not natural-language inference:
  they can reject a faithful paraphrase that shares few words, but cannot accept a statement whose
  words and figures aren't in the source. Added `WikiContextTool` (free, CC BY-SA) as the second
  tool. Checked live on one question (an 82-94 s run became 193 s, the extra time being two short
  model decisions plus a second search, and it found the town's official tourism page the first pass
  missed); not yet benchmarked.
- **Milestone 15:** worldwide coverage. The system had only been exercised on two US neighborhoods, so
  it was probed against 15 places on every inhabited continent (`evaluation/global_coverage.py`, which
  anyone can re-run) and the defects fixed: English-only search (14 of 15 places returned only English
  sources) now supplemented by local-language search on the place's native-script name
  (`app/tools/locale.py`, `app/planning/local_queries.py`); substring keyword matching that planned
  *nightlife* for "Barcelona"; a topic set built around a US college student (added attractions,
  climate, customs, healthcare, and visitor and newcomer personas); islands and beaches treated as
  businesses; a pin 158 km off for "Sukhumvit, Bangkok"; official sources recognised only as `.gov` /
  `.edu`; Latin-only text and digit handling in the verification checks; right-to-left rendering; and
  an Overpass server that failed for 6 of 15 places. Local-language search exposed a real cost: the
  free translator takes ~11 ms per character on a laptop CPU, which made one live run exceed 25
  minutes, so translation is now limited to pages that mention the place (checked on the original
  text), 6 per search, and their first 700 characters. Live runs on four places finished in 135-330 s.
  Known limits, stated in the README: languages the translator has no pack for get English-only search;
  an ambiguous name (in Arabic "Zamalek" is also a football club) can surface irrelevant pages, which
  the claim checks then mostly exclude; not a benchmark of answer quality.
- **Milestone 16:** removing invented data from the product. An audit found that on an install with no
  keys, asking about Harvard Square returned 12 fabricated sources (`.example.net` URLs, publisher
  "(fixture)") and 8 claims marked *supported*, with a confident summary and no warning, and that the
  landing page showed a made-up sample answer citing real domains that were never checked. Both are
  gone: the fixture documents, their tools and the `/api/locations` demo-places endpoint moved to
  `tests/` (nothing under `app/` may reference them; a test enforces that), unconfigured tools return
  nothing and say so, `LLMClaimExtractor` no longer falls back to canned claims, and the landing page
  describes what a response contains without asserting anything about a place. Also removed the unused
  `FakeLLMService`, and merged two duplicate copies of the resolver-chain builder.

