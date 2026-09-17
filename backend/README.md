# Backend — LocationResearchAgent

The research pipeline described in [`docs/architecture.md`](../docs/architecture.md). By
default it runs fully free and mostly offline: fixture-backed tools, rule-based planning,
keyword retrieval, local SQLite storage. Setting `ANTHROPIC_API_KEY` and/or `TAVILY_API_KEY`
opts into LLM-backed reasoning and live web search respectively (independent of each other);
having `sentence-transformers` installed opts into hybrid semantic retrieval automatically. See
below for all three.

## What this does and doesn't do

**Does:** resolve a location, decompose a question into research topics (adaptively — a
nightlife-only question does not trigger housing research), retrieve and score evidence
(lexically, and semantically if available), extract claims and link them to the evidence that
supports them, verify those claims (including a coarse cross-source contradiction check), and
synthesize a transparent, cited answer with a full execution trace. Claim verification is always
a fixed, deterministic step — never LLM-backed, and it never moves in the pipeline — regardless
of which other components are in use (see `docs/research-workflow.md`).

**Doesn't:** real geocoding (location resolution is still fixture/alias-based), or a second,
broadened search attempt when a topic comes back empty. Both are flagged explicitly where
relevant rather than silently assumed away.

**Fixture data is synthetic.** Everything under `fixtures/` was written for this project to test
the pipeline. It does not describe real, current conditions at Harvard Square or Davis Square and
must not be treated as such outside local development.

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

**`TAVILY_API_KEY`** — opts into real web search + page retrieval
(`TavilyWebSearchTool`/`TavilyPageRetrievalTool`) in place of the fixture tools. Tavily has a free
tier; heavier usage is billed by Tavily. **Setting this alone collects real evidence but produces
no claims** — `FixtureClaimExtractor` can't read real page text, so set `ANTHROPIC_API_KEY` too if
you want live search to actually produce claims. See `docs/research-workflow.md`'s "Live search"
section for what this looks like in practice (verified against the real API).

Either key can be set independently of the other. `app/agents/factory.py` detects both
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
  models/       Pydantic schemas shared by every layer
  core/         config (incl. .env loading), LLMService + AnthropicLLMService, shared LLM JSON parsing
  tools/        LocationResolver / WebSearch / PageRetrieval interfaces + fixture and Tavily implementations
  planning/     topic taxonomy + KeywordResearchPlanner + LLMResearchPlanner
  retrieval/    EvidenceRetriever interface + keyword, semantic, and hybrid implementations
  evidence/     EvidenceRepository (in-memory, SQLite) + evidence enrichment (quality/recency)
  synthesis/    claim extraction (fixture- or LLM-based) + answer synthesis (template- or LLM-based)
  verification/ checks every claim against the evidence store before it can be marked "supported",
                plus a deterministic cross-claim contradiction check (always non-LLM)
  agents/       LocationResearchAgent — orchestrates the bounded lifecycle, plus the default-agent
                factory (auto-selects rule-based/fixture vs. LLM-backed/live components per API key)
  api/          FastAPI route
fixtures/       synthetic locations + source documents, keyed by location slug and topic id
evaluation/     the benchmark from docs/evaluation.md, actually runnable (`run_benchmark.py`)
tests/          pytest suite: planner, retrieval (keyword/semantic/hybrid), evidence repository
                (in-memory/SQLite), verification (incl. contradiction), agent end-to-end, API,
                and the LLM-backed and Tavily components (against fakes, never live)
```
