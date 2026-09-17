# Frontend — demonstration UI (Milestone 7)

A thin React + TypeScript client for the `LocationResearchAgent` backend. This is deliberately
secondary to the backend: it does no research logic of its own — it sends a location + question
to `POST /api/research` and renders exactly what comes back (summary, recommendation, the
research plan, claims with their verification status, evidence grouped by topic with citations,
limitations, and the full research trace), plus a Leaflet/OpenStreetMap pin at the resolved
location. No map API key is needed — OpenStreetMap tiles are free.

## Setup

```bash
npm install
npm run dev
```

Opens on `http://localhost:5173`. It expects the backend running on `http://localhost:8000`
(see [`../backend/README.md`](../backend/README.md)); override with a `VITE_API_BASE_URL` env
var if yours is elsewhere. The backend's CORS config (`app/main.py`) currently only allows
`localhost:5173` — a local-dev setting, not a production policy.

## What you'll see

- With no API keys set on the backend: fixture-only results for Harvard Square / Davis Square,
  fast and deterministic.
- With `TAVILY_API_KEY` set: real web evidence, but **no claims** (see
  `../docs/research-workflow.md`'s "Live search" section for why).
- With both `TAVILY_API_KEY` and `ANTHROPIC_API_KEY` set: real evidence *and* real claims, with
  verification status (supported / contradicted / insufficient evidence) shown per claim.

## Build

```bash
npm run build
```

Type-checks (`tsc -b`) then produces a static build in `dist/`.
