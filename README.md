# Lugensa AI — Agentic Location Web Intelligence System

An agentic research system that investigates public information about a place to answer a
natural-language question about it — e.g. *"Would Harvard Square, Cambridge, MA be a good place
for a college student?"* — and produces a transparent, evidence-backed, cited assessment instead
of a generic recommendation. The map and chat UI are a demonstration environment; the research
agent itself is the project.

## Contents

- [Overview](#overview)
- [Features](#features)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [Testing](#testing)
- [Evaluation](#evaluation)
- [Status](#status)
- [Documentation](#documentation)

## Overview

Given a location and a question, the agent:

1. Resolves the location.
2. Plans which research topics are actually relevant to the question (not a fixed checklist).
3. Retrieves evidence for each topic — from local fixtures by default, or live web search
   and real community/forum commentary when configured.
4. Extracts and verifies claims against that evidence, including a cross-source contradiction
   check.
5. Synthesizes a cited, hedged answer — never a confident-sounding guess with no source behind
   it — and reports what it couldn't confirm.

Everything above runs **free and offline by default** (fixture-backed tools, rule-based
planning, local SQLite storage). Two things are opt-in: live web search (`TAVILY_API_KEY`) and
LLM-backed reasoning (`ANTHROPIC_API_KEY`) — see [Configuration](#configuration).

## Features

- **Adaptive planning** — a narrow question ("what's the nightlife like?") researches one topic;
  a broad one researches several. Topic selection is keyword-based by default, LLM-based if
  `ANTHROPIC_API_KEY` is set.
- **Hybrid retrieval** — keyword scoring by default, blended with local-embedding semantic
  scoring (`sentence-transformers`, no API key) when installed.
- **Real community voices** — a dedicated view of actual forum/review commentary (Reddit,
  Nextdoor, Google Maps, etc.) about the location, including negative or mixed opinions and
  recent incident reports, shown for awareness rather than filtered out.
- **Verification, not vibes** — claim status (supported / contradicted / insufficient evidence)
  is decided by a fixed, deterministic verifier — never by whichever component proposed the
  claim, and never by an LLM, regardless of which other components are LLM-backed.
- **Honest degradation** — every fallback (no LLM, no live search, an API failure, an
  off-topic result filtered out) is recorded in the response's `limitations`, not hidden.
- **A real evaluation, not just a plan** — [`docs/evaluation.md`](docs/evaluation.md) has actual
  numbers from a real benchmark run, including where the system did *not* win.

## Quick start

Two terminals.

**Backend:**

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev -- --port 3000
```

Open `http://localhost:3000`. Full details, troubleshooting, and what each part does are in
[`backend/README.md`](backend/README.md) and [`frontend/README.md`](frontend/README.md).

## Configuration

Nothing below is required — the app is fully functional with none of it set. Copy
`backend/.env.example` to `backend/.env` to configure any of it (gitignored, never committed).

| Variable | Enables | Notes |
|---|---|---|
| `TAVILY_API_KEY` | Live web search + real community/forum evidence | Free tier available at [tavily.com](https://tavily.com) |
| `ANTHROPIC_API_KEY` | LLM-backed planning, claim extraction, and synthesis | Billed per Anthropic's normal usage pricing |
| `DISABLE_SEMANTIC_RETRIEVAL` | Forces keyword-only retrieval | Set to `1` to skip loading the local embedding model |

Setting `TAVILY_API_KEY` alone collects real evidence but produces no claims — the fixture-based
claim extractor can't read real page text. Set `ANTHROPIC_API_KEY` too for live search to
actually produce claims. See [`docs/research-workflow.md`](docs/research-workflow.md).

## Project structure

```
backend/     LocationResearchAgent, FastAPI app, fixtures, tests, evaluation harness
frontend/    React + TypeScript UI (landing page, map search, chat-driven research workspace)
docs/        architecture.md, research-workflow.md, evaluation.md
```

See [`backend/README.md`](backend/README.md) for the backend's internal layout.

## Testing

```bash
cd backend
pytest
```

The suite is free, offline, and deterministic by construction — an autouse fixture forces real
API keys and semantic retrieval off during tests regardless of local `.env` configuration, so
`pytest` never makes a real network call or spends API credits.

## Evaluation

```bash
cd backend
python -m evaluation.run_benchmark
```

Runs the benchmark described in [`docs/evaluation.md`](docs/evaluation.md) for real — Baseline B
vs. the proposed system's orchestration — and prints/saves actual measured results, including
tradeoffs where the proposed system does *not* clearly win (e.g. more tool calls, more latency,
occasionally less source diversity). Requires `TAVILY_API_KEY`.

## Status

All 8 originally-planned milestones are implemented: adaptive planning, hybrid retrieval,
persistent evidence storage, claim verification with contradiction detection, live web search,
optional LLM reasoning, a React frontend, and a real (not hypothetical) evaluation run. See the
Milestone status table in [`docs/architecture.md`](docs/architecture.md) for what's opt-in vs.
free-by-default, and [`docs/evaluation.md`](docs/evaluation.md) for what's still unmeasured
(Baseline A and claim-level metrics require an `ANTHROPIC_API_KEY` that hasn't been available in
this environment).

## Documentation

- [`backend/README.md`](backend/README.md) — run the agent and its API, environment variables,
  what each backend module does
- [`frontend/README.md`](frontend/README.md) — run the demo UI
- [`docs/architecture.md`](docs/architecture.md) — design, interfaces, and what's opt-in vs. free
- [`docs/research-workflow.md`](docs/research-workflow.md) — the research lifecycle in detail
- [`docs/evaluation.md`](docs/evaluation.md) — the evaluation plan and its actual results

## License

See [`LICENSE`](LICENSE).

## Author

Anish Kuila
