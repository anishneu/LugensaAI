# Frontend — demonstration UI

A React + TypeScript client for the `LocationResearchAgent` backend. This is deliberately
secondary to the backend: it does no research logic of its own — it sends a location + question
to `POST /api/research` and renders exactly what comes back, plus a couple of independent,
backend-driven surfaces (live POI search, the regional live feed). No map or geocoding API key is
needed anywhere — OpenStreetMap tiles and Nominatim are free.

## Setup

```bash
npm install
npm run dev -- --port 3000
```

Opens on `http://localhost:3000`. It expects the backend running on `http://localhost:8000`
(see [`../backend/README.md`](../backend/README.md)); override with a `VITE_API_BASE_URL` env
var if yours is elsewhere. The backend's CORS config (`app/main.py`) allows `localhost:3000` — a
local-dev setting, not a production policy.

## Pages

- **Landing (`/`)** — a "Get Started" entry point into the app.
- **Workspace (`/app`)** — everything else:
  - A map-based **search** (`LocationSearchInput`) that merges the two curated demo neighborhoods
    with live point-of-interest results from `GET /api/places/search` (debounced 350ms, min 3
    characters) — any real business or address, not just a neighborhood. Picking one exact result
    passes its coordinates straight through on every subsequent question, so the backend never
    has to re-resolve the name as text (see `../backend/README.md`'s POI section for why that
    matters).
  - A **chat sidebar** — ask a question, see it appended to this location's history (persisted
    in `localStorage`, keyed by the normalized location query).
  - The **response panel** — tabs for Overview (summary, key findings, question-organized
    details, the research plan), Community (real forum/review commentary about the *specific*
    selected place, cleaned of site chrome — never an embedded raw scrape), Claims (with
    verification status), Evidence (every source, sortable), and Details (limitations + the full
    execution trace).
  - The **live feed sidebar** (`LiveFeedSidebar`) — a completely independent surface, fetched
    from `GET /api/live-feed` on its own, unrelated to any question asked. It reports on the
    broader region the selected place is in, not the place itself (see
    `../backend/README.md`'s "Live feed" section) — refreshing shows what's recently happening
    in the area, which is deliberately not the same content as the Community tab. Auto-refreshes
    every `AUTO_REFRESH_MS` (3 minutes, in `LiveFeedSidebar.tsx`) since every fetch is a real,
    billed Tavily search; a manual refresh button covers "I want it now". Results are paginated
    client-side (5 per page, up to 3 pages) from the single fetched batch — changing pages never
    re-fetches.

## What you'll see

- With no API keys set on the backend: fixture-only results for Harvard Square / Davis Square,
  fast and deterministic; live POI search and the live feed are both still available (they only
  need free Nominatim / `TAVILY_API_KEY` respectively, not an LLM key).
- With `TAVILY_API_KEY` set: real web evidence and a real live feed. The Overview can still
  produce a real, evidence-grounded answer without an LLM key (`TemplateSynthesizer` quotes the
  most relevant, credible excerpt per topic), but claim extraction from real page text needs an
  LLM — see the next bullet.
- With `TAVILY_API_KEY` and (`ANTHROPIC_API_KEY` or `OLLAMA_ENABLED`) set: real evidence *and*
  real claims, with verification status (supported / contradicted / insufficient evidence) shown
  per claim, and an LLM-drafted Overview that reasons across claims and raw evidence together.

## Build

```bash
npm run build
```

Type-checks (`tsc -b`) then produces a static build in `dist/`. `npm run lint` runs `oxlint`.
