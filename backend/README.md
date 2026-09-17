# Backend — LocationResearchAgent

The research pipeline described in [`docs/architecture.md`](../docs/architecture.md). By
default it runs fully free and mostly offline: fixture-backed tools, rule-based planning,
keyword retrieval, local SQLite storage. Setting `ANTHROPIC_API_KEY`/`OLLAMA_ENABLED` and/or
`TAVILY_API_KEY` opts into LLM-backed reasoning and live web search respectively (independent of
each other); having `sentence-transformers` installed opts into hybrid semantic retrieval
automatically. See below for all of these.

## What this does and doesn't do

**Does:** resolve a location — either of the two curated fixture neighborhoods instantly, or any
other real point of interest via live geocoding (`NominatimLocationResolverTool`, free, opt-out
via `DISABLE_LIVE_GEOCODING=1`) — decompose a question into research topics (adaptively — a
nightlife-only question does not trigger housing research), retrieve and score evidence
(lexically, and semantically if available), extract claims and link them to the evidence that
supports them, verify those claims (including a coarse cross-source contradiction check), and
synthesize a transparent, cited answer — a direct summary, key findings, and question-organized
details, not just a claims list — with a full execution trace. Claim verification is always a
fixed, deterministic step — never LLM-backed, and it never moves in the pipeline — regardless of
which other components are in use (see `docs/research-workflow.md`).

**Doesn't:** a second, broadened search attempt when a per-topic research search comes back
empty — it stays as originally queried, and the gap is recorded in `limitations` rather than
silently retried. (The independent live feed is a different, deliberately regional query from the
start — see below — not a fallback triggered by an empty result.)

**Fixture data is synthetic.** Everything under `fixtures/` was written for this project to test
the pipeline. It does not describe real, current conditions at Harvard Square or Davis Square and
must not be treated as such outside local development.

## Overview synthesis: evidence in, reasoning, an answer out

Early on, the Overview was gated entirely behind atomic claim extraction: no successfully
extracted claim meant no answer, just "insufficient evidence" — even when real, useful evidence
had been collected. Two changes fixed this:

1. **`LLMClaimExtractor` grounds claims by more than trusting a citation.** The LLM is asked to
   cite the evidence id/topic it used, and that citation is used directly when it validates. When
   it doesn't (a smaller model reliably fails this exact instruction — e.g. citing a source name
   it noticed inside the passage, like `"FBI Uniform Crime Reporting data"`, instead of the
   literal `[evidence_id]` token it was shown), `_best_matching_evidence()` recovers grounding
   deterministically: it checks the claim's own wording against the real evidence text via
   lexical overlap, and only keeps the claim if that independent check clears a high bar. Either
   way, a claim's grounding is *checked*, never assumed from the LLM's self-report.
2. **`Synthesizer.synthesize()` sees the full evidence, not only claims that survived extraction.**
   `LLMSynthesizer`'s prompt is given verified claims *and* raw, per-topic evidence excerpts
   (labeled by source type, publisher, and date), with instructions to reason across both:
   prefer concrete facts/numbers, treat review/forum content as opinion rather than fact, present
   a "contradicted" claim as unresolved disagreement, never state a fact the evidence doesn't
   support, and — for safety/incident questions specifically — never claim something "hasn't
   happened" or "is safe" from a mere absence of search hits; say what the sources checked did
   and didn't turn up, with the time window, instead. `TemplateSynthesizer` (the free, non-LLM
   fallback) does the deterministic version of the same idea: for a topic with evidence but no
   claim, it quotes the single most relevant *and* credible excerpt (blending relevance with a
   source-type quality score) rather than reporting only a gap.

Both synthesizers still never get to invent a limitation — coverage gaps, per-claim caveats, and
the contradiction-detection caveat are computed in code (`deterministic_limitations()`) and
appended regardless of what either synthesizer wrote.

## Live feed: regional, not location-specific

`GET /api/live-feed` (`TavilyLiveFeedTool`) is a separate, unverified surface: "what's happening
recently in the broader area", independent of both the Q&A pipeline and the specific selected
place. It's deliberately not "what's being said about this exact business" — a single POI (one
Starbucks branch, one specific cafe) rarely has anything published about it by name in the last
week, so both the search query and the relevance filter are anchored on the area (the selected
place's city, or region if no city is known — derived dynamically, never hardcoded) rather than
the place's own name. The relevance check also requires that anchor to appear in a result's title,
or be repeated in its body — a single passing mention (e.g. a national sports thread that
name-checks a city once) isn't enough to count as regional activity. Results are deduplicated by
URL and sorted newest-first; the frontend paginates the returned list (5 items/page, up to 3 pages
shown) without any extra requests per page. Every fetch (initial load, manual refresh, or the
frontend's periodic auto-refresh) is one real, billed Tavily search — see the frontend's refresh
interval in `frontend/README.md` before making it more aggressive.

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate   # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`sentence-transformers` (semantic retrieval) pulls in `torch` and downloads a small model on
first use (~90MB, cached after). To skip that entirely, remove it from `requirements.txt` before
installing, or just set `DISABLE_SEMANTIC_RETRIEVAL=1` (the app still runs fine without it —
keyword-only retrieval).

## Run the API

```bash
uvicorn app.main:app --reload
```

Then:

```bash
curl -X POST http://127.0.0.1:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{"location": "Harvard Square, Cambridge, MA", "question": "Would this be a good place for a college student?"}'
```

Try `"What'\''s the nightlife like around here?"` for the same location to see the planner select
a completely different, smaller set of topics. Or skip curl entirely and use the frontend
(`../frontend/README.md`).

## Optional: API keys (`.env`)

Copy `.env.example` to `.env` (gitignored, never committed) and fill in whichever keys you have —
`app/core/config.py` loads it automatically, so you don't need to `export` anything by hand:

```bash
cp .env.example .env
```

**`ANTHROPIC_API_KEY`** — opts into `LLMResearchPlanner`, `LLMClaimExtractor`, and
`LLMSynthesizer` in place of the rule-based/fixture-based defaults. Billed per Anthropic's normal
usage pricing once set (the default model, `claude-haiku-4-5`, is inexpensive; override with
`ANTHROPIC_MODEL`).

**`OLLAMA_ENABLED`** — a free, local alternative to `ANTHROPIC_API_KEY` for the same three
components, via [Ollama](https://ollama.com) running on this machine. No API key, no per-token
billing, but it needs Ollama installed and a model pulled first:

```bash
# 1. install Ollama (see ollama.com/download for macOS/Linux/Windows installers)
# 2. pull a model once (a few GB download; llama3.1 is the default)
ollama pull llama3.1
# 3. make sure the server is running (the installer usually starts this automatically)
ollama serve
# 4. in backend/.env:
OLLAMA_ENABLED=1
```

Override the model with `OLLAMA_MODEL` (must match a model you've pulled) and the server address
with `OLLAMA_BASE_URL` (default `http://localhost:11434`). If `ANTHROPIC_API_KEY` is also set,
Anthropic takes priority — see `app/agents/factory.py`. Inference speed and quality depend entirely
on this machine's hardware and the model chosen; a smaller model (e.g. `llama3.2` or a `:3b`-class
model) trades quality for speed if the default is too slow.

**CPU-only inference is genuinely slow, not a bug** — measured on one CPU-only machine (no GPU
offload), claim extraction over ~12 evidence passages (the largest of the three LLM-backed calls,
since it includes every retrieved passage's full text) took 3.5–6 minutes; the planner and
synthesizer calls are smaller and noticeably faster. `OLLAMA_TIMEOUT_SECONDS` (default `600`)
gives each call generous headroom before falling back to the deterministic path — raise it further
if a call is timing out on slower hardware, or lower it if you'd rather fail fast to the free
rule-based fallback than wait minutes per question. A GPU-backed Ollama install is dramatically
faster if available.

**Model size is a real tradeoff for claim extraction specifically**, measured on the same machine
with real live-search evidence: `llama3.1` (8B) sometimes cites evidence ids correctly and produces
real grounded claims, but not reliably — the same evidence sometimes yields grounded claims and
sometimes doesn't, and each attempt costs several slow CPU-bound minutes. `llama3.2:3b` is roughly
3x faster but consistently failed to copy the literal `[evidence_id]` token verbatim — it
substitutes a source name it noticed inside the passage text instead (e.g. writing `"FBI Uniform
Crime Reporting (UCR) data"` instead of `"tavily:safety:982ec06c37ea"`), even with an explicit
worked example added to the system prompt (`_SYSTEM_PROMPT` in `app/synthesis/llm_claim_extractor.py`).
`LLMClaimExtractor`'s grounding safeguard correctly drops every one of those miscited claims and
falls back rather than showing a fabricated citation, so this never produces a wrong answer — it
just means claim extraction with a 3B-class model will consistently report "insufficient evidence"
even when the planner/synthesizer's own LLM-generated topic reasoning and prose are working fine.
There isn't a known prompt fix for this within the 3B class; a larger model is the lever that
actually helps, at the cost of speed.

**`TAVILY_API_KEY`** — opts into real web search + page retrieval
(`TavilyWebSearchTool`/`TavilyPageRetrievalTool`) in place of the fixture tools. Tavily has a free
tier; heavier usage is billed by Tavily. **Setting this alone collects real evidence but produces
no claims** — `FixtureClaimExtractor` can't read real page text, so set `ANTHROPIC_API_KEY` or
`OLLAMA_ENABLED` too if you want live search to actually produce claims. See
`docs/research-workflow.md`'s "Live search" section for what this looks like in practice (verified
against the real API).

Any of these can be set independently of the others. `app/agents/factory.py` detects all of them
automatically. Every LLM-backed component falls back to its deterministic counterpart on any
failure — a bad response, a network error, a rejected/ungrounded output — and records why in the
response's `limitations`, so a flaky call degrades the run rather than crashing it.

## Run the tests

```bash
pytest
```

The test suite never calls a real external API or loads a real embedding model, **even if `.env`
has real keys and `sentence-transformers` is installed** — an autouse fixture in
`tests/conftest.py` forces both API keys off, semantic retrieval off, and evidence storage into a
per-test temp file. LLM-backed components are tested against a scripted fake `LLMService`
(`tests/llm_doubles.py`); Tavily against a fake client (`tests/test_tavily_tools.py`); semantic
retrieval against a fake embedding function (`tests/test_semantic_retriever.py`). The suite is
always free, offline, fast, and deterministic regardless of local machine configuration.

## Evaluation

```bash
python -m evaluation.run_benchmark
```

Runs the benchmark from [`../docs/evaluation.md`](../docs/evaluation.md) for real (Baseline B vs.
the proposed system, both against live Tavily search) and prints/saves actual metrics — not just
the plan. Requires `TAVILY_API_KEY`; results and their scope (what could and couldn't be measured
without an `ANTHROPIC_API_KEY`) are written up in that doc.

## Layout

```
app/
  models/       Pydantic schemas shared by every layer (incl. PlaceCandidate for live POI search)
  core/         config (incl. .env loading), LLMService + AnthropicLLMService + OllamaLLMService,
                shared LLM JSON parsing
  tools/        LocationResolver / WebSearch / PageRetrieval interfaces + fixture, Tavily, and
                Nominatim (POI geocoding/search, TavilyLiveFeedTool) implementations, plus
                FallbackLocationResolver (composite.py)
  planning/     topic taxonomy + KeywordResearchPlanner + LLMResearchPlanner
  retrieval/    EvidenceRetriever interface + keyword, semantic, and hybrid implementations
  evidence/     EvidenceRepository (in-memory, SQLite) + evidence enrichment (quality/recency)
  synthesis/    claim extraction (fixture- or LLM-based, with deterministic grounding recovery for
                the LLM path) + answer synthesis (template- or LLM-based, from claims *and* raw
                evidence — see "Overview synthesis" below)
  verification/ checks every claim against the evidence store before it can be marked "supported",
                plus a deterministic cross-claim contradiction check (always non-LLM)
  agents/       LocationResearchAgent — orchestrates the bounded lifecycle, plus the default-agent
                factory (auto-selects rule-based/fixture vs. LLM-backed/live components per API key)
  api/          FastAPI routes, incl. /api/places/search (live POI autocomplete) and
                /api/live-feed (independent, region-scoped recent activity)
fixtures/       synthetic locations + source documents, keyed by location slug and topic id
evaluation/     the benchmark from docs/evaluation.md, actually runnable (`run_benchmark.py`)
tests/          pytest suite: planner, retrieval (keyword/semantic/hybrid), evidence repository
                (in-memory/SQLite), verification (incl. contradiction), agent end-to-end, API,
                and the LLM-backed and Tavily components (against fakes, never live)
```
