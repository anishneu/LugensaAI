# Frontend — demonstration UI

A React + TypeScript client for the `LocationResearchAgent` backend. This is deliberately
secondary to the backend: it does no research logic of its own — it sends a location + question
to `POST /api/research` and renders exactly what comes back, plus a couple of independent,
backend-driven surfaces (live POI search, the regional live feed). No map or geocoding API key is
needed anywhere — OpenStreetMap tiles and Nominatim are free.

Styling is Tailwind CSS (v4, via `@tailwindcss/vite` — no separate config file, configured
entirely in `src/index.css`) layered on top of the existing CSS-variable theme in `index.css`
(the `@layer base` wrapper there matters: Tailwind utilities live in `@layer utilities`, and an
unlayered rule always wins over a layered one regardless of specificity, so the old global
`h1`/`a` color rules have to be layered too or they'd silently beat any text-color utility).
The landing page (`pages/LandingPage.tsx`) is a deliberately quiet editorial layout: a light/dark
warm palette scoped to `.landing` in `index.css`, a serif headline, one static sample answer, and
Framer Motion used only for a light scroll-reveal (it respects `prefers-reduced-motion`). An earlier
version had an animated three.js network background and a dark purple-gradient look; both were
removed as generic, along with the `three` dependency.

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

- **Landing (`/`)** — the entry point: a sample answer (clearly labeled illustrative, not a live
  query), the five pipeline steps, and what the app will and won't do. No fabricated social proof
  (testimonials, user counts, logos).
- **Workspace (`/app`)** — everything else:
  - A map-based **search** (`LocationSearchInput`) that merges the two curated demo neighborhoods
    with live point-of-interest results from `GET /api/places/search` (debounced 350ms, min 3
    characters) — any real business or address, not just a neighborhood. Picking one exact result
    passes its coordinates straight through on every subsequent question, so the backend never
    has to re-resolve the name as text (see `../backend/README.md`'s POI section for why that
    matters).
  - Once a location is picked, `WorkspaceHeader` renders it as a full-width map banner (the
    pinned location as the top of the page, not a small inset thumbnail) with the place name and
    controls overlaid on a gradient for legibility over arbitrary map tiles.
  - An **"Around this pin"** card (`NearbyCard`): food, transit, groceries, health, police, and
    banking places near the pin with computed walking distances, straight from OpenStreetMap map
    data (`GET /api/places/nearby`) — not AI-generated, and labeled as such. A single sliding
    row with arrow buttons (scrollbars are hidden app-wide), so it never pushes the answer down.
  - For a specific business, an **"On Google Maps"** card (`PlaceProfileCard`): rating, review
    count, hours, and dated review cards with the original of any translated review one click away
    (`GET /api/places/profile`). When the server isn't connected to Google it says so instead of
    silently showing less.
  - A **chat sidebar** — ask a question, see it appended to this location's history (persisted
    in `localStorage`, keyed by the normalized location query).
  - The **response panel** — tabs for Overview (summary, key findings, question-organized
    details, the research plan), Community (real forum/review commentary about the *specific*
    selected place, cleaned of site chrome — never an embedded raw scrape), Claims (with
    verification status), Evidence (every source, sortable), and Details (limitations + the full
    execution trace).
  - **Translation labels** (`TranslationNote`): evidence in another language is machine-translated
    to English by the backend and marked "Machine-translated from Japanese" with the original one
    click away; text that couldn't be translated is marked "not translated" rather than shown as
    if it were readable.
  - The **live feed sidebar** (`LiveFeedSidebar`) — a completely independent surface, fetched
    from `GET /api/live-feed` on its own, unrelated to any question asked. It reports on the
    broader region the selected place is in, not the place itself (see
    `../backend/README.md`'s "Live feed" section) — refreshing shows what's recently happening
    in the area, which is deliberately not the same content as the Community tab. Each item shows
    its own publication time, both relative ("2 hours ago") and exact ("Posted Sep 17, 6:56 PM");
    the backend drops anything without a real publication date, so no item is ever stamped with
    the time it happened to be fetched. Auto-refreshes every `AUTO_REFRESH_MS` (10 minutes, in
    `LiveFeedSidebar.tsx`) since every fetch is several real, billed Tavily searches; a manual
    refresh button covers "I want it now". Results are paginated client-side (5 per page, up to
    3 pages) from the single fetched batch — changing pages never re-fetches.
  - While a question runs, the response panel shows a **live elapsed timer** alongside a rough
    expected range from `GET /api/capabilities`, which varies by orders of magnitude depending on
    whether a local model is doing the reasoning.

## What you'll see

- With no API keys set on the backend: fixture-only results for Harvard Square / Davis Square,
  fast and deterministic; live POI search and the live feed are both still available (they only
  need free Nominatim / `TAVILY_API_KEY` respectively, not an LLM key).
- With `TAVILY_API_KEY` set: real web evidence and a real live feed. The Overview can still
  produce a real, evidence-grounded answer without an LLM key (`TemplateSynthesizer` quotes the
  most relevant, credible excerpt per topic), but claim extraction from real page text needs an
  LLM — see the next bullet.
- With `TAVILY_API_KEY` and `OLLAMA_ENABLED` set: real evidence *and*
  real claims, with verification status (supported / contradicted / insufficient evidence) shown
  per claim, and an LLM-drafted Overview that reasons across claims and raw evidence together.

## Build

```bash
npm run build
```

Type-checks (`tsc -b`) then produces a static build in `dist/`. `npm run lint` runs `oxlint`.
