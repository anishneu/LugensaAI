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
- **Headless UI** for the interactive pieces that need real accessibility: `Tab` (the answer's underlined tabs, the browser-style place tabs, live feed
  tabs), `Popover` (opening hours), `Dialog` (the "Around this pin" detail pop-up), `Disclosure` (the research trace). The place search
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
was decoration that cost about 130 KB gzipped. The search screen is back to a live street-map backdrop, a different
world city each visit, under a dark overlay, drifting slowly up and down on its own (about 26 s a sweep, eased at each
turn; not started for anyone with reduced motion set) and fading in once it has drawn its first frame. The landing page
has no moving map at all. What else moves is a CSS `transition` on hover and focus, the spinner and the progress bar
while a question runs.

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
  nav with the app button at the far right; a hero over a **still image** of a street map (`assets/landing-map.webp`, 254 KB, rendered once
  from OpenFreeMap's style of OpenStreetMap data and dimmed under a gradient). It is an image because the live map beneath
  the landing page could come up blank on a refresh or a first visit, and it is decoration; the footer credits the map data
  in general terms (OpenStreetMap contributors), and every map inside the app keeps its own credit control. Two buttons, with no search box, because the app opens on one; a preview of the workspace's layout
  drawn with placeholder bars (`AnswerPreview`: top bar, map and question box, the two browser-style tabs, the underlined
  answer tabs, the live feed); a strip naming where the evidence comes from; tabs for
  what you can ask (trip, move, business; a question clicked there opens the app with it waiting in the question box, and
  is never run for you); three numbers that are facts about the design (about 60 countries searched in the local language, five steps,
  no billed model API), not a customer base; the five steps; principles and honest limits; an FAQ (`Faq`, a Headless UI
  `Disclosure`); a closing call to action. It has no testimonials, user counts, customer logos or invented sample answer:
  an earlier version showed one, with real-looking sources that had never been checked, which is what this project exists
  not to do. Layout took cues from Foursquare (dark, one coloured word in the headline, tabs by audience), Ressio's Mason
  (a product window under the hero) and ElevenLabs/NewsAI (large type, few words). The footer carries the copyright line
  (© year, Anish Kuila, all rights reserved).
- **Workspace (`/app`)** — the search screen, then the research view. Arriving from the landing page it opens
  straight on the place chosen there (router state: `location`, or `submitQuery` for typed text, plus an optional
  `question` that is put in the question box and never run for you; the search screen says a question is waiting):
  - A **search** screen (`SearchHero`) over a live, slowly drifting street-map backdrop (`MapBackdrop`) and a live place search (`LocationSearchInput`, from
    `GET /api/places/search`, debounced 350 ms, min 3 characters) — any real business or address, not just
    a neighborhood. Picking one exact result passes its coordinates straight through on every subsequent
    question, so the backend never has to re-resolve the name as text (see `../backend/README.md`'s POI
    section for why that matters).
  - A **top navigation bar** (`TopNav`): the project name and the chosen location on the left, "Change
    location" on the right.
  - Three columns beneath it (stacked on a phone). **Left:** a zoomed-in map of the pin (`MapPanel`, labels
    in English first with the local script beneath; clicking it, not dragging it, or the button on it, opens
    that place in Google Maps in a new window: its listing, by Google's own place id when the pin was picked from a
    Google result (`pinMapsUrl`), else a search for its name or address centered on the pin. A bare coordinate link
    opened a pin titled with numbers, which looked like a different spot from the listing though it was the same point) and the **"Ask the agent"** box (`ChatSidebar`), whose question history is saved in
    `localStorage` per location. **Centre:** the answer. **Right:** the live feed.
  - The **answer** (`ResponsePanel`): a verdict banner, then tabs for Overview (summary, key findings,
    question-organized details, the research plan), Community (real forum/review commentary about the
    *specific* selected place, cleaned of site chrome — never an embedded raw scrape; filterable by site, with
    counts, and "Mixed sources" by default, which takes one voice from each site in turn so Google Maps, which can
    supply most of them, doesn't bury Reddit, TripAdvisor and the forums; long quotes are cut to six lines with
    "Read more"), Claims (with
    verification status), Evidence (every source, sortable by relevance or date) and Details (limitations + the full research
    trace). Evidence in English, or machine-translated to English, is listed before local-language sources.
  - A **place panel** (`components/place/`) of two **browser-style tabs** (`BrowserTabs`, shaped in `index.css` with plain CSS:
    rounded tops, and the selected tab flows into the panel through two concave feet, as in a real browser): Google Maps and
    Around this pin. It is a different shape from the answer's underlined tabs and the live feed's pills on purpose: these are
    sources for the place, not sections of one answer. A tab carries its rating or count beside its name when the panel is
    wide enough (a container query hides it when not). The chevron at the end folds the panel; every tab stays mounted, so
    the unselected one keeps loading and keeps its number current.
    - **Google Maps** (`GoogleMapsBody`, data from `useGoogleData`): for a business, its rating and star row, review count,
      price, a link to Google Maps, Google's own summary in full, and every review Google returns (up to five) in full in a
      list that scrolls with a visible scrollbar (`.scroll-visible`; the app hides scrollbars elsewhere), with the original
      of any translated review one click away. **Open now / Closed now** sits beside the review count and opens a small
      window with the week's hours. For a
      pin that is a landmark rather than a business (a temple), the same listing is shown when a well-known place within
      80 m has the pin's exact name, with "Also popular nearby" beneath. For an area or a corner, which is not one place,
      it lists the best-known rated places around it (`GET /api/places/popular`). Hidden when the server isn't connected to
      Google (`GET /api/capabilities`). **When the answer replaces the area's list with a specific place's own reviews**
      (it named or adopted one), the Google Maps tab gets a pulsing dot (and "Updated" in the tab when there is room), a
      line inside says which place now fills it, and a folded panel opens. The dot clears when the tab is clicked, the line
      when dismissed; the reader is never switched away from the other tab. The first load of a place's reviews is not
      flagged, only a replacement.
    - **Around this pin** (`NearbyTab`): a compact grid of categories (food, transit, groceries, health, police,
      banking), each with its count and nearest place, from OpenStreetMap map data (`GET /api/places/nearby`), not
      AI-generated and labeled so. Each opens a **pop-up** listing every place found (up to 15) with all the data the
      map has (address, hours, phone, website, cuisine). Each place's **Map** link (`placeMapsUrl` in `maps.ts`) is a Google
      Maps search for its name (and street) centered on its coordinates, which opens the real listing and picks the branch
      on that spot; coordinates alone opened a bare pin titled with the numbers. Bus stops, tram stops and subway entrances
      keep the exact-coordinate pin, because a name search matched other things when tried. When the public map servers are busy it says so and offers
      "Try again" (the backend tries five servers and falls back to an earlier answer first). When names or addresses
      are in another language, a **Translate to English** button appears (`POST /api/places/translate`): English shown
      first with the original beneath, labeled as machine translation, since a machine translation of a name is a gloss
      (it turned one Kyoto police box into "North America"). Where the country isn't English-speaking, names in the Latin
      script are offered too ("Bundespolizeiinspektion Erfurt" becomes "Federal Police Inspectorate Erfurt"); Latin-script
      addresses are never translated, because a street name is a proper noun.
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

## Notes worth knowing

- **Saved questions** are loaded when a place opens and written back only after they were loaded for that place. Before,
  the empty starting list was written over the saved one whenever effects ran twice (React's dev mode does), which lost
  every saved question on a reload.
- **Landing page performance.** Scroll lag came from blur filters over a moving page: a sticky `backdrop-blur` header
  re-blurred every frame over a WebGL map, and a 54 rem glow blurred by 140 px. Those are now gradients, and the landing map
  is a still image, so nothing on that page re-draws while it scrolls. The search screen's map draws at pixel ratio 1
  without fade blending and is taken out of compositing while it is off screen (an `IntersectionObserver`); the landing
  sections below the fold use `content-visibility: auto`.
- **Vite can serve a stale module** after a burst of file writes (an edited component kept rendering its old markup
  across reloads until the dev server was restarted). If the page doesn't match the code, restart `npm run dev`.

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
