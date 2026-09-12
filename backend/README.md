# Backend — LocationResearchAgent (Milestone 1)

A deterministic, fixture-backed implementation of the research pipeline described in
[`docs/architecture.md`](../docs/architecture.md). No API key or network access is required —
every tool reads from local JSON fixtures under `fixtures/`.

## What this milestone does and doesn't do

**Does:** resolve a location, decompose a question into research topics (adaptively — a
nightlife-only question does not trigger housing research), retrieve and score evidence,
link claims to the evidence that supports them, verify those claims, and synthesize a
transparent, cited answer with a full execution trace.

**Doesn't yet:** call an LLM for planning/synthesis/claim-extraction (all rule-based/template-based
for now — see the docstrings in `app/planning/planner.py`, `app/synthesis/synthesizer.py`, and
`app/synthesis/claim_extractor.py`), detect contradictions between sources, or retrieve from the
live web. These are flagged explicitly in every response's `limitations` field and are planned for
later milestones (see [`docs/architecture.md`](../docs/architecture.md)).

**Fixture data is synthetic.** Everything under `fixtures/` was written for this project to test
the pipeline. It does not describe real, current conditions at Harvard Square or Davis Square and
must not be treated as such outside local development.

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate   # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

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
a completely different, smaller set of topics.

## Run the tests

```bash
pytest
```

## Layout

```
app/
  models/       Pydantic schemas shared by every layer
  core/         config + the LLMService interface (unused by M1's pipeline; a seam for M2)
  tools/        LocationResolver / WebSearch / PageRetrieval interfaces + fixture implementations
  planning/     topic taxonomy + the rule-based ResearchPlanner
  retrieval/    EvidenceRetriever interface + keyword (lexical) scoring
  evidence/     EvidenceRepository (in-memory) + evidence enrichment (quality/recency)
  synthesis/    claim extraction (from fixture-annotated evidence) + template-based answer synthesis
  verification/ checks every claim against the evidence store before it can be marked "supported"
  agents/       LocationResearchAgent — orchestrates the bounded lifecycle, plus the default-agent factory
  api/          FastAPI route
fixtures/       synthetic locations + source documents, keyed by location slug and topic id
tests/          pytest suite: planner, retrieval, evidence repository, verification, agent end-to-end, API
```
