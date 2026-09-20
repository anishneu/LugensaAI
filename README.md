# Lugensa AI — Agentic Location Web Intelligence System

[![CI](https://github.com/anishneu/agentic-ai-location-web/actions/workflows/ci.yml/badge.svg)](https://github.com/anishneu/agentic-ai-location-web/actions/workflows/ci.yml)

An agentic research system that investigates public information about a place to answer a
natural-language question about it — e.g. *"Would Harvard Square, Cambridge, MA be a good place
for a college student?"* or *"Is there a bar near this specific Starbucks, and how safe is the
area?"* — and produces a transparent, evidence-backed, cited assessment instead of a generic
recommendation. The map and chat UI are a demonstration environment; the research agent itself is
the project.

## Contents

- [Overview](#overview)
- [Features](#features)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [Testing](#testing)
- [Continuous integration](#continuous-integration)
- [Evaluation](#evaluation)
- [Status](#status)
- [Documentation](#documentation)

## Overview

Given a location and a question, the agent:

1. Resolves the location.
2. Plans which research topics are actually relevant to the question (not a fixed checklist).
3. Retrieves evidence for each topic from live web search (including community and forum
   commentary), Wikipedia and Wikivoyage, OpenStreetMap and, optionally, Google Places.
4. Extracts and verifies claims against that evidence, including a cross-source contradiction
   check.
5. Synthesizes a cited, hedged answer — never a confident-sounding guess with no source behind
   it — and reports what it couldn't confirm.

Real research needs two things, both free: live web search (`TAVILY_API_KEY`, free tier) and
LLM-backed reasoning through a local model, `OLLAMA_ENABLED` (needs [Ollama](https://ollama.com)
installed; nothing leaves your machine, and there is no billed model API anywhere in the project)
— see [Configuration](#configuration). **Nothing is faked:** with neither set, the app runs but has
nothing to search, returns no evidence or claims, and says so in every response. It never falls back
to made-up sample data.

## Features

- **Any real place** — search resolves any point of interest (a specific business, address,
  building, or Google Maps plus code) via Google Places when configured, else free OpenStreetMap
  Nominatim. Picking one exact result from live search is passed straight
  through to research without being re-resolved as text, so a same-named place nearby can't be
  silently substituted.
- **Works for places in any language** — search results come back with English names, and
  foreign-language sources are machine-translated to English (free, local, via Argos Translate),
  labeled as translated, with the original one click away. Nearby food, transit, shops, health
  and police come from OpenStreetMap map data, not from an LLM.
- **Searches in the local language too** — an English query only finds English pages. For a place in
  a country whose web is written in another language, the agent also searches in that language using
  the place's native-script name, and matches pages on it. For a restaurant in Kurume, Japan this
  turned 3-4 sources (before, the English search had returned pages about a *different* hotel in
  Kyoto) into 10, seven of them Japanese pages about the right restaurant. About 60 countries have a
  curated language; English-speaking countries are searched in English; see
  [Working in any country](backend/README.md#working-in-any-country) for exactly what is and isn't
  covered, and `python -m evaluation.global_coverage` to check it yourself.
- **Adaptive planning** — a narrow question ("what's the nightlife like?") researches one topic;
  a broad one researches several. Topic selection is keyword-based by default, LLM-based if
  `OLLAMA_ENABLED` is set.
- **A specific business is researched as a business** — a cafe or hotel is searched by name, and a
  page only counts as evidence if it names the business's distinguishing words *and* the right
  city (so "SR Coffee" in Tokyo can't be answered with reviews of "SR Coffee" in Virginia). No
  soft fallback: another business's reviews are worse than an honest "nothing found".
- **Google Maps ratings wherever a place has them, without having to ask for them** — a general question ("is it a
  good place to visit as a tourist?") about a temple, a museum or a business gets its Google rating and reviews as
  evidence, and the rating opens the key findings. An address pin adopts the most popular place at it (the address of
  Ginkaku-ji is the temple), a corner adopts the venue the question names ("how are the reviews of this AO Arena?"),
  and an area, which is not one place, shows the best-known places around it with Google's ratings instead of
  attaching a neighbour's. The reviews appear beside those from TripAdvisor, Reddit and regional forums.
- **Google Maps data for that business (optional)** — with `GOOGLE_PLACES_API_KEY`, its rating,
  review count, hours and Google's own review summary become cited evidence and get a card in the
  UI, clearly labeled as Google's. **"Around this pin"** (food, transit, groceries, health, police,
  banks with computed walking distances) comes from OpenStreetMap map data, not from an LLM. The public
  Overpass servers are often slow for a dense city centre, so it tries five of them with their own timeouts,
  falls back to an earlier answer for that spot, and offers "Try again" rather than a dead end. Names and addresses in
  another script (Japanese, Chinese, Korean, Cyrillic, Arabic, Thai) can be translated to English on request with the
  free local translator, labeled as machine translation with the original beneath.
- **Hybrid retrieval** — keyword scoring by default, blended with local-embedding semantic
  scoring (`sentence-transformers`, no API key) when installed.
- **Real community voices** — a dedicated view of actual forum/review commentary (Reddit,
  Nextdoor, Google Maps, etc.), filterable by site and mixed across sites by default so one large source cannot bury the rest, about the specific selected location, including negative or mixed
  opinions and recent incident reports, shown for awareness rather than filtered out. Relevance is
  checked against the exact place (city and region, not just a same-named city elsewhere, and not
  just a chain's name with no city context) rather than the softer per-topic filter every other
  topic uses. Timestamps are never invented: a real publication date is shown when the source
  provides one — including one recovered from the page's own text (e.g. a review site's "Reviewed
  <date>" line) when the search API's own date field is empty — and every other item is labeled
  by when it was *retrieved*, explicitly, rather than shown with a fake "posted" time.
- **Forums, communities and regional sites, not only Google** — besides web search, each run searches the
  places where people actually talk about a place: Reddit, Quora, TripAdvisor and others everywhere, plus the
  country's own forums and review sites (PTT, Dcard and Pixnet in Taiwan, Naver in Korea, Tabelog in Japan,
  Pantip in Thailand, about 30 countries in all; `backend/app/tools/community_sources.py`). Those forums are
  searched separately, in the place's own language, because an English query never reaches them: with the
  native name and a topic ("台北101 觀景台 心得") a live run returned 8 relevant PTT and Pixnet threads.
  Evidence is shown English first (native English, or machine-translated), with the local-language original
  secondary and labeled.
- **Every post carries its real date where the source states one** — the search API gives none for forums,
  so it is read from the post: PTT's creation time is in the URL, Reddit's comes from a public archive of
  Reddit's own timestamps (one request for all threads), and blogs' from their page metadata
  (`backend/app/tools/post_dates.py`). A live run dated all 8 regional threads and all 8 Reddit threads.
  Where a source refuses a plain request (Dcard, Facebook, Instagram, TikTok, X: login walls and bot checks)
  the post is shown as "date unknown", never given a made-up one.
- **An independent live feed about the place's city** — separate from the Q&A pipeline and from the
  Community tab. News from the last 30 days plus community conversation about the place's own city; when
  the exact area has little it widens once to the region around it and labels those items as such, and never
  to the whole country. Every news item carries its *own* publication time (news with no real date is
  dropped); community posts without one say "date unknown". Built to be cheap on the free Tavily plan: 2 to 4
  searches on a cold load, 0 when cached for an hour, and the search for a city is shared by every place in it
  (`backend/README.md`, "What a feed load costs"). Never generated or reshuffled.
- **Readable descriptions, not page chrome** — a search snippet is markup, timestamps, bylines and menus joined
  together. The live feed and the evidence cards show whole sentences picked out of it (`backend/app/tools/descriptions.py`),
  never rewritten, and just the headline and source when no sentence qualifies.
- **An interface built to be read** — a landing page over a still street-map image (search happens in the app); then
  a top bar, a zoomed-in map and question box on the left, the answer in the middle, the live feed on the right,
  built with Tailwind and Headless UI over MapLibre and free OpenFreeMap tiles (no API key). No animation or 3D
  library: they were tried and removed. See [`frontend/README.md`](frontend/README.md).
- **Evidence-grounded answers, not reflexive "insufficient evidence"** — the Overview reasons over
  the full retrieved evidence (not only whatever survived atomic claim extraction), producing a
  direct answer, key findings, and question-organized details, while still never stating a fact
  the evidence doesn't support and never asserting an absolute safety claim ("no crime has ever
  happened here") from a mere absence of search hits.
- **Verification, not vibes** — claim status (supported / contradicted / insufficient evidence)
  is decided by a fixed, deterministic verifier — never by whichever component proposed the
  claim, and never by an LLM, regardless of which other components are LLM-backed. Claim
  grounding itself is also enforced deterministically: a claim is kept only if its cited evidence
  id validates, or its own wording is independently matched against real evidence text — never on
  an LLM's self-reported citation alone.
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
| `OLLAMA_ENABLED` | LLM-backed planning, claim extraction, and synthesis, via a local model | Free, but needs [Ollama](https://ollama.com) installed and a model pulled — see `backend/README.md` for which model, and why "thinking" mode must be off on CPU |
| `GOOGLE_PLACES_API_KEY` | Google Maps rating, hours and dated reviews for one specific business (or a venue the question names), used as cited evidence | Optional and off by default: needs a Google Cloud project with billing enabled. See `backend/README.md` |
| `DISABLE_TRANSLATION` | Turns off translation of foreign-language evidence to English | Translation is on when `argostranslate` and `langdetect` are installed (free, local; language packs download on first use) |
| `DISABLE_POST_DATE_FETCH` | Stops reading forum posts' dates from the web | Set to `1` to use only the dates carried in URLs (PTT, dated blog paths); Reddit and page-metadata dates need a small request each (no search credits) |
| `DISABLE_SEMANTIC_RETRIEVAL` | Forces keyword-only retrieval | Set to `1` to skip loading the local embedding model — the single biggest startup cost |

Setting `TAVILY_API_KEY` alone collects real evidence but produces no claims — reading claims out
of real pages needs a model, and the response says so. Set `OLLAMA_ENABLED` too for live search to
actually produce claims. See [`docs/research-workflow.md`](docs/research-workflow.md).

## Project structure

```
backend/     LocationResearchAgent, FastAPI app, tests, evaluation harness
frontend/    React + TypeScript UI (landing page, map-backdrop search, three-column research workspace with a MapLibre map)
docs/        architecture.md, research-workflow.md, evaluation.md
```

See [`backend/README.md`](backend/README.md) for the backend's internal layout.

## Testing

```bash
cd backend
pytest          # over 400 tests
cd ../frontend
npm run lint && npx tsc -b && npm run build
```

The backend suite is free, offline, and deterministic by construction (its invented sample sources live
only in `backend/tests/fixtures` and are never served by the app; a test enforces that) — an autouse fixture forces real
API keys and semantic retrieval off during tests regardless of local `.env` configuration, so
`pytest` never makes a real network call or spends API credits.

## Continuous integration

Everything under [`.github/workflows/`](.github/workflows/) runs on `ubuntu-latest` and needs no
secrets of yours — the test suite's autouse fixture forces every real key and optional feature off,
so CI is free, offline and deterministic just like a local `pytest`.

| Workflow | When | What it does |
|---|---|---|
| [`ci.yml`](.github/workflows/ci.yml) | every push and PR to `main`/`develop` | **Backend lint** (ruff: syntax errors, undefined names, unused imports/variables), **backend tests** (full `pytest`, with CPU-only PyTorch so the runner doesn't download CUDA), **frontend** (`npm ci`, `oxlint`, `tsc -b` + production build, build uploaded as an artifact). A newer push cancels the older run. |
| [`codeql.yml`](.github/workflows/codeql.yml) | push, PR, weekly | GitHub's static security analysis of the Python backend and the TypeScript frontend. |
| [`secret-scan.yml`](.github/workflows/secret-scan.yml) | every push and PR | Gitleaks over the full history, because a key committed once and deleted later is still leaked. |
| [`dependency-audit.yml`](.github/workflows/dependency-audit.yml) | PRs, weekly, manual | Dependency review on PRs (blocks newly introduced high-severity issues), plus `pip-audit` and `npm audit` on what is actually installed. |
| [`release.yml`](.github/workflows/release.yml) | pushing a `v*` tag | Re-runs tests, lint and build from that exact commit, then publishes a GitHub Release with generated notes and the frontend bundle attached. Never releases untested code. |
| [`dependabot.yml`](.github/dependabot.yml) | monthly | Grouped update PRs for pip, npm and the workflows themselves. |

**Why CodeQL failed on a private repository, and what was changed.** The analysis ran (it scanned every file) and then
the step after it failed with "Resource not accessible by integration ... get-a-workflow-run". On a private repo the
CodeQL action reads its own workflow run through the API, which needs the `actions: read` permission; the workflow
granted only `contents: read` and `security-events: write`. It now grants `actions: read`. On a pull request from
**Dependabot** the same message has a second cause that no workflow setting fixes: Dependabot's token is read-only, so it
can never upload results. The CodeQL job therefore skips Dependabot's PRs (the push and weekly scans cover the same
code). The same read-only token is why the dependency review no longer posts a PR comment, and why the secret scan now
asks for `pull-requests: read` (gitleaks lists a PR's commits through the API). The dependency review still runs only on
a public repository or when the repository variable `CODE_SCANNING` is `true`, because on a private repo it needs the
dependency graph (Advanced Security). If the CodeQL upload is refused with "Advanced Security must be enabled", restore
the same condition on it.

Dependabot opens at most one grouped, minor-and-patch PR per ecosystem a month (two for pip and npm at a time) and no
major-version bumps; its PRs are ordinary PRs, safe to close (`@dependabot close`) or merge once CI is green.

These have been validated with `actionlint` and their commands run locally, but a workflow only
proves itself on GitHub — the first run of each is the real test.

One accepted exception: `pip-audit` runs with `--ignore-vuln PYSEC-2026-3075` (a `stanza` advisory). `stanza`
is pinned below the fixed version by `argostranslate`, which does the free local translation, so it can't be
upgraded without dropping that feature. The reason is written next to the flag in
[`dependency-audit.yml`](.github/workflows/dependency-audit.yml); remove it once Argos allows
`stanza >= 1.12.2`. CodeQL and the PR dependency review need GitHub itself and could not be reproduced locally.

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

The 8 originally planned milestones are implemented (adaptive planning, hybrid retrieval, persistent
evidence storage, claim verification with contradiction detection, live web search, optional LLM
reasoning, a React frontend, and a real evaluation run), followed by live place search, an
independent live feed (news plus community for the city, widening once to its region), real
per-item timestamps, forum and regional-community sources with their real dates, translation of foreign-language sources,
business-specific research, OpenStreetMap "around this pin" data, and optional Google Maps data (including a venue
named in the question), readable feed descriptions and a rebuilt interface. See
the Milestone status table in [`docs/architecture.md`](docs/architecture.md) for what's opt-in vs.
free-by-default.

**What it is, honestly:** a RAG pipeline with a small, bounded agent loop. It retrieves live web
evidence, reranks, grounds, generates and verifies with citations. After the first search pass the
agent *looks at what it found and decides what to do next*: search again with a query aimed at the
question, or consult Wikipedia/Wikivoyage, at most twice (`AgentConfig.max_research_rounds`). The model
makes that choice when one is available; a rule-based judge does otherwise. It is a bounded loop over
a fixed menu of two tools, not an open-ended autonomous agent: it does not write code, browse
freely, or plan across questions. Claims written by the model are checked against the words and
figures of the sources they cite, and overview sentences that no source backs are flagged as the
model's inference. What that check is and isn't is in [`docs/architecture.md`](docs/architecture.md).
[`docs/evaluation.md`](docs/evaluation.md) covers what has and hasn't been measured (Baseline A and
claim-level metrics are not measured; the new loop has been checked on one live question, not
benchmarked).

## Documentation

- [`backend/README.md`](backend/README.md) — run the agent and its API, environment variables,
  what each backend module does
- [`frontend/README.md`](frontend/README.md) — run the UI: its stack, the landing page and the workspace, and the
  map pitfalls found along the way
- [`docs/architecture.md`](docs/architecture.md) — design, interfaces, and what's opt-in vs. free
- [`docs/research-workflow.md`](docs/research-workflow.md) — the research lifecycle in detail
- [`docs/evaluation.md`](docs/evaluation.md) — the evaluation plan and its actual results

## License

See [`LICENSE`](LICENSE).

## Author

Anish Kuila
