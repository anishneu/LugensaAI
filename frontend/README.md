# Frontend — demonstration UI

A React + TypeScript client for the `LocationResearchAgent` backend. This is deliberately
secondary to the backend: it does no research logic of its own — it sends a location + question
to `POST /api/research` and renders exactly what comes back, plus a couple of independent,
backend-driven surfaces (live place search, "around this pin", the live feed). No map or geocoding API key is
needed anywhere: the map is MapLibre GL over free [OpenFreeMap](https://openfreemap.org) vector tiles
(OpenStreetMap data), and geocoding is Nominatim.

## Stack

- **Tailwind CSS v4** (`@tailwindcss/vite`, configured in `src/index.css`, no config file) for all
  styling. There are no per-component CSS files; the colours are CSS variables in `index.css`
  (`--bg`, `--text-h`, `--accent`, `--supported`, ...) with a dark variant on `prefers-color-scheme`,
  used as Tailwind arbitrary values (`bg-[var(--bg-alt)]`). Those base rules sit in `@layer base`:
  an unlayered rule beats a layered utility regardless of specificity, so unlayered `h1`/`a` colour
  rules would silently override text-colour utilities.
- **Headless UI** for the interactive pieces that need real accessibility: `Tab` (response tabs, live feed
  tabs), `Dialog` (the "Around this pin" detail pop-up), `Disclosure` (the research trace). The place search
  box is hand-written (keyboard-navigable list). **Heroicons** for icons.
- **MapLibre GL** for both maps (`MapPanel.tsx` for the pin, `MapBackdrop.tsx` behind the search box), each
  lazy-loaded. They always use OpenFreeMap's light style, also in dark mode: its dark style rendered as
  near-black with unreadable labels, and a map is something to read. Vite needs the worker URL set explicitly
  (`mapSetup.ts`, `setWorkerUrl(... ?worker&url)`): left to itself MapLibre looks for its worker next to the
  bundled library, does not find it, and the map stays blank with no error. One more MapLibre trap: its
  stylesheet is unlayered, so it beats Tailwind utilities on the map's own element (`position: relative`
  defeats `absolute inset-0`); the element that fills a page is a wrapper and the map fills that.
- React Router, Vite 8, `oxlint`.

There is no animation library and no 3D library. Both were tried (framer-motion transitions, and a three.js
globe on the search screen) and removed: the transitions added nothing a CSS `transition` doesn't, and the globe
was decoration that cost about 130 KB gzipped. The search screen is back to a street-map backdrop, a different
world city each visit, under a dark overlay. What still moves is a CSS `transition` on hover and focus, the
spinner and the progress bar while a question runs.

## Setup

```bash
npm install
npm run dev -- --port 3000
```

Opens on `http://localhost:3000` (Vite's default 5173 also works). It expects the backend running on `http://localhost:8000`
(see [`../backend/README.md`](../backend/README.md)); override with a `VITE_API_BASE_URL` env
var if yours is elsewhere. The backend's CORS config (`app/main.py`) allows ports 3000 (used here) and 5173 (Vite's default) on `localhost` — a
local-dev setting, not a production policy.

## Pages

- **Landing (`/`)** — a dark, single-page product page (`pages/LandingPage.tsx`, with `components/landing/`): a sticky
  nav; a hero over a real street map (the same `MapBackdrop` as the search screen) with the working place search in it,
  so a place chosen there opens the workspace directly, and typed text is looked up once on arrival; a preview of an
  answer's *shape* drawn with placeholder bars (`AnswerPreview`); a strip naming where the evidence comes from; tabs for
  what you can ask (trip, move, business; a question clicked there waits in the workspace's question box and is never run
  for you); three numbers that are facts about the design (about 60 countries searched in the local language, five steps,
  no billed model API), not a customer base; the five steps; principles and honest limits; an FAQ (`Faq`, a Headless UI
  `Disclosure`); a closing call to action. It has no testimonials, user counts, customer logos or invented sample answer:
  an earlier version showed one, with real-looking sources that had never been checked, which is what this project exists
  not to do. Layout took cues from Foursquare (dark, one coloured word in the headline, tabs by audience), Ressio's Mason
  (a product window under the hero) and ElevenLabs/NewsAI (large type, few words).
- **Workspace (`/app`)** — the search screen, then the research view. Arriving from the landing page it opens
  straight on the place chosen there (router state: `location`, or `submitQuery` for typed text, plus an optional
  `question` that is put in the question box and never run for you):
  - A **search** screen (`SearchHero`) over a street-map backdrop (`MapBackdrop`) and a live place search (`LocationSearchInput`, from
    `GET /api/places/search`, debounced 350 ms, min 3 characters) — any real business or address, not just
    a neighborhood. Picking one exact result passes its coordinates straight through on every subsequent
    question, so the backend never has to re-resolve the name as text (see `../backend/README.md`'s POI
    section for why that matters).
  - A **top navigation bar** (`TopNav`): the project name and the chosen location on the left, "Change
    location" on the right.
  - Three columns beneath it (stacked on a phone). **Left:** a zoomed-in map of the pin (`MapPanel`, labels
    in English first with the local script beneath; clicking it, not dragging it, opens that spot in Google
    Maps in a new window) and the **"Ask the agent"** box (`ChatSidebar`), whose question history is saved in
    `localStorage` per location. **Centre:** the answer. **Right:** the live feed.
  - The **answer** (`ResponsePanel`): a verdict banner, then tabs for Overview (summary, key findings,
    question-organized details, the research plan), Community (real forum/review commentary about the
    *specific* selected place, cleaned of site chrome — never an embedded raw scrape), Claims (with
    verification status), Evidence (every source, sortable by relevance or date) and Details (limitations + the full research
    trace). Evidence in English, or machine-translated to English, is listed before local-language sources.
  - An **"Around this pin"** card (`NearbyCard`): food, transit, groceries, health, police and banking
    places near the pin with computed walking distances, from OpenStreetMap map data
    (`GET /api/places/nearby`) — not AI-generated, and labeled as such. When the public map servers are busy the card says so and offers "Try again" (the backend tries five servers and falls back to an earlier answer before it gives up). Each category opens a **pop-up** listing every place found (up to 15) with all
    the data OpenStreetMap has for it — address, opening hours, phone, website, cuisine — rather than only
    a name and a distance. Fields nobody added to the map are simply absent, and the pop-up says so.
  - For a specific business, an **"On Google Maps"** card (`PlaceProfileCard`): rating, review count,
    hours, and dated review cards with the original of any translated review one click away
    (`GET /api/places/profile`). When the server isn't connected to Google it says so instead of silently
    showing less. If the pin was not a business but the question named one beside it ("how are the reviews of this
    AO Arena?"), the answer comes back with that business as its location, and the header and this card switch to it.
  - **Translation labels** (`TranslationNote`): evidence in another language is machine-translated to
    English by the backend and marked "Machine-translated from Japanese" with the original one click away;
    text that couldn't be translated is marked "not translated" rather than shown as if it were readable.
  - The **live feed** (`LiveFeedSidebar`) — independent of any question, fetched from `GET /api/live-feed`.
    It shows news from the last 30 days and community conversation (forums, Reddit) about the place's city;
    when the city itself has little it widens once to the region around it and labels those items ("Wider
    region · Taipei City"). It never goes country-wide. Each item shows its own publication time when it has
    one, relative ("2 days ago") with the exact time on hover; community posts show the date read from
    the post itself (PTT's URL, a Reddit archive, page metadata) and are listed newest first; one whose date
    can't be read (Dcard, login-walled sites) says "date unknown" and is never given one. A load is 2 to 4 billed Tavily searches (plus free date lookups) and the server caches it
    for an hour (see `../backend/README.md`, "What a feed load costs"), so it auto-refreshes every
    `AUTO_REFRESH_MS` (60 minutes, in `LiveFeedSidebar.tsx`), which is free while the cache is warm. The
    refresh button passes `refresh=true` to force a fresh search, and is the only thing that does. Each card shows the
    headline, then the source site as a link, then a readable description: whole sentences picked out of the
    page snippet by the backend (`app/tools/descriptions.py`), not the raw markup and navigation. If no sentence
    qualifies the card shows just the headline and source. Items are paged client-side (6 at a time) from
    the one fetched batch.
  - While a question runs, the response panel shows a **live elapsed timer** alongside a rough expected
    range from `GET /api/capabilities`, which varies by orders of magnitude depending on whether a local
    model is doing the reasoning.

## What you'll see

- With no API keys set on the backend: no evidence and no claims, with a limitation saying live
  search isn't configured (there is no built-in sample data); place search works through free
  Nominatim, and the live feed needs `TAVILY_API_KEY`.
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
