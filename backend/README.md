# Backend — LocationResearchAgent

The research pipeline described in [`docs/architecture.md`](../docs/architecture.md). By
default it runs fully free and mostly offline: fixture-backed tools, rule-based planning,
keyword retrieval, local SQLite storage. Setting `OLLAMA_ENABLED` and/or `TAVILY_API_KEY` opts
into LLM-backed reasoning (a free local model) and live web search respectively (independent of
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

## What makes a run slow

Run time is dominated by two things, in this order:

1. **Loading the semantic-retrieval model.** `sentence-transformers` reads a
   real model off disk, which takes about a minute. A fresh retriever is built
   per research run, so this used to be paid on *every* request; it's now
   cached per process (`_MODEL_CACHE` in
   `app/retrieval/semantic_retriever.py`), making it a one-time cost on the
   first request after a restart. Measured with the LLM off, the same run took
   **67.4s cold and 6.3s warm** — so this caching is worth roughly 10x on
   every request after the first. `DISABLE_SEMANTIC_RETRIEVAL=1` removes the
   cost entirely, at the price of keyword-only retrieval.
2. **LLM inference, if an LLM is enabled.** Minutes on a CPU, seconds to a minute or two
   on a GPU (see "Choosing the local model" below). Reading the prompt dominates, which is why
   the claim-extraction prompt caps each evidence passage
   (`_MAX_EVIDENCE_CHARS_FOR_EXTRACTION`) and `best_excerpt` picks the relevant passage of a
   page rather than shipping full page extracts.

Per-topic web searches run concurrently (`_MAX_SEARCH_WORKERS` in
`app/agents/location_research_agent.py`), so N topics cost roughly one search
round trip rather than N. Only the searches are parallel — scoring, evidence
enrichment, and the SQLite writes stay on one thread and in topic order, so
results remain deterministic.

`GET /api/capabilities` reports which of these are active along with a rough
expected duration range, which the UI shows beside a live elapsed timer while
a question runs.

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

**`OLLAMA_ENABLED`** — opts into `LLMResearchPlanner`, `LLMClaimExtractor` and `LLMSynthesizer` in
place of the rule-based/fixture-based defaults, using a model running on this machine through
[Ollama](https://ollama.com). No API key, no per-token billing, and nothing leaves the machine. The
project has no billed model API by design.

```bash
# 1. install Ollama (ollama.com/download)
# 2. pull the model once (~19GB)
ollama pull qwen3:30b
# 3. in backend/.env:
OLLAMA_ENABLED=1
```

Override the model with `OLLAMA_MODEL` (it must be pulled) and the server with `OLLAMA_BASE_URL`
(default `http://localhost:11434`). If a call fails or times out (`OLLAMA_TIMEOUT_SECONDS`, default
600), that component falls back to its deterministic counterpart and says so in `limitations`.

### Choosing the local model

Measured on one laptop (Intel i7-1255U, 64GB RAM, integrated Iris Xe graphics, no dedicated GPU),
not assumed. The "one call" rows use a realistic ~2,800-token prompt, cold (model load included):

| Model | One call, CPU only | One call, integrated GPU |
|---|---|---|
| `llama3.2:3b` | 227 s | **42 s** |
| `llama3.1` (8B) | 450 s | 100 s |
| `gpt-oss:20b` | 329 s | 92 s |
| `qwen3:30b` (thinking off) | 470 s | **127 s** |

Three findings drove the choice:

1. **Reading the prompt is the cost, not writing.** On this CPU a model reads 8–15 tokens/s whatever
   its size, so time scales with prompt length (a business question sends ~2.8k tokens across the
   three calls, a neighbourhood question ~6k). The integrated GPU reads at 40–120 tokens/s. A quick
   test on a 48-token prompt showed 226 tokens/s and was badly misleading; always time a real prompt.
2. **"Thinking" mode must be off.** `qwen3:30b` took 233 s for a trivial request with it on and 6.7 s
   with it off, for an extract-and-summarize task that gains nothing from reasoning. `OLLAMA_THINK`
   defaults to `false`; models with no thinking mode accept and ignore it.
3. **A mixture-of-experts model is bigger for free.** `qwen3:30b` holds 30B parameters of knowledge
   but activates ~3B per token, so it writes about as fast as a small model. End to end through the
   real pipeline on the same question and hardware:

   | | `qwen3:30b` | `llama3.2:3b` |
   |---|---|---|
   | Time, business question | 192 s | 182 s |
   | Claims produced | 3, each traceable to a source | 13, several padding ("has a pleasant atmosphere") |
   | Time, neighbourhood question | 259 s | not run |

   So the bigger model cost no extra time and gave a more precise answer. One caveat: claim grounding
   is a lexical check against real evidence text, so a weaker model's plausible-but-unsourced claims
   can still pass it; a stronger model mostly avoids producing them in the first place.

**Make Ollama use the integrated GPU (Windows).** This is what turns 15+ minutes into ~3–4. Ollama
skips integrated GPUs unless told otherwise. Set these user environment variables, then restart
Ollama:

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_VULKAN", "1", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_IGPU_ENABLE", "1", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION", "1", "User")
```

Check with `ollama ps`: the `PROCESSOR` column should read `100% GPU`. With no GPU at all, expect
`qwen3:30b` to take roughly 15–25 minutes per question; set `OLLAMA_MODEL=llama3.2:3b` (about 8
minutes on CPU) if that's too slow. Other settings: `OLLAMA_NUM_CTX` (default 8192; Ollama
truncates silently past the window), `OLLAMA_KEEP_ALIVE` (default `30m`, so the 25–40 s model load
isn't repeated after a short break).

Hosted free tiers were considered and not adopted: Groq's free tier, for example, allows roughly
100K tokens/day on its 70B model (about ten questions), and sends the research to a third party.

**`TAVILY_API_KEY`** — opts into real web search + page retrieval
(`TavilyWebSearchTool`/`TavilyPageRetrievalTool`) in place of the fixture tools. Tavily has a free
tier; heavier usage is billed by Tavily. **Setting this alone collects real evidence but produces
no claims** — `FixtureClaimExtractor` can't read real page text, so set `OLLAMA_ENABLED` too if
you want live search to actually produce claims. See
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
`tests/conftest.py` forces every API key and optional feature off, semantic retrieval off, and evidence storage into a
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
without the LLM-backed components) are written up in that doc.

## Layout

```
app/
  models/       Pydantic schemas shared by every layer (incl. PlaceCandidate for live POI search)
  core/         config (incl. .env loading), LLMService + OllamaLLMService,
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

## Nearby places (OpenStreetMap, not AI)

`GET /api/places/nearby?latitude=&longitude=&radius_m=` lists food, transit, groceries, health,
police, and banking places around a pin, each with a computed distance, via the free Overpass API
(`app/tools/overpass_tool.py`). It exists because "is there a bar / station / pharmacy nearby" is
a factual question the LLM should not be the source of: every item is a real map feature, so it
can't be hallucinated. Two honest limits, both shown in the UI: it is only as complete as
OpenStreetMap's volunteer mapping, and OSM has no ratings, reviews, or live opening hours — those
still come from web sources and are only as reliable as they are. Google's Places API would
supply them but needs a billing account, and scraping Google Maps breaks its terms, so it isn't
used. Returns 503 when `DISABLE_LIVE_GEOCODING=1`, 502 if Overpass is down.

Location search only treats a *trailing* US state ("Boston, MA 02122", "Cambridge MA") as a
signal to restrict results to the US. Scanning every word was a bug: "hotel in Tokyo" read "in" as
Indiana and returned New York hotels.

## Translation (any language to English)

A place in Japan, Germany or Russia is mostly written about in that language, so evidence and live
feed items in other languages are machine-translated to English before the rest of the pipeline
sees them (`app/tools/translation.py`). It runs locally with Argos Translate: free, no API key,
and nothing about the research leaves the machine. Language is detected with `langdetect`
(ignored below 90% confidence), and each language's pack (~100MB) downloads the first time it is
needed, so the first Japanese page in a fresh install is slow and later ones are not.

Translating happens *before* the relevance filters, because a Japanese page doesn't spell the
place the way an English query does. It also means retrieval, claim extraction and synthesis all
work on English. The original title and text are kept in `Evidence.metadata`
(`original_title`, `original_text`, `language`) and the UI labels every translated item as
machine-translated with the original one click away. If a pack can't be downloaded, the original
text is kept and flagged "not translated"; it is never dropped or faked. Nominatim is asked for
English place names (`accept-language=en`), and a missing prefecture/state is recovered from the
address text (a Tokyo address has none in the structured fields).

Limits: machine translation is imperfect (it can flatten tone and mistranslate idiom), quality
varies by language, and at most 20 items per search are translated. Optional like semantic
retrieval: skip the two packages in `requirements.txt` or set `DISABLE_TRANSLATION=1` to turn it off.

## Researching one specific business (a cafe, a hotel)

A business is not a neighborhood, and treating it like one produced wrong answers: area-style
queries ("... restaurants cafes food scene") returned roundups of *other* cafes in the same city,
and one of them was cited as evidence about the cafe actually asked about. So a location now
carries `is_business` (from OpenStreetMap's category: amenity, shop, tourism, craft, ...), and for
a business:

- The plan searches for that business by name (`"<name>" <city> customer reviews ...`) instead
  of the area templates (`business_query_templates` in `app/planning/topics.py`).
- A page counts as evidence only if it names the business's *distinguishing* words (not "coffee" or
  "bar", which every cafe shares) **and** the right city or region (`_mentions_business`,
  `_mentions_place_context` in `tavily_tools.py`). There is no soft fallback: another business's
  reviews are worse than none, so the honest result is "nothing found".
- If fewer than three web pages mention it, a limitation says coverage is thin.

The model also no longer reads only the first few hundred characters of each page (usually site
navigation). `app/synthesis/excerpt.py` picks the passage that matches the question instead; it
only selects text, never rewrites it.

### Google Maps ratings and reviews (optional)

For one specific business, open-web search finds a couple of pages while Google Maps has hundreds
of dated reviews, and no amount of prompting closes that gap. Setting `GOOGLE_PLACES_API_KEY`
adds Google's rating, review count, price level, hours and up to five recent reviews (each with its
real post date, translated to English by Google with the original kept) as ordinary cited
evidence, and shows them in a card (`GET /api/places/profile`).

It is off by default because it needs a Google Cloud project **with billing enabled** (a card on
file); the reviews fields are in a paid tier with a monthly free allowance, so check current
pricing. One lookup per place is cached for 30 minutes. A result is used only if it is within
400 m of the pin and carries the business's name words. Google's API returns at most five reviews
per place, so the rating reflects all of them and the quotes only some; the UI says so.
`app/tools/google_places_tool.py` is written against Google's documented response shape and is
covered by mocked tests, but has not been run against the live API from this repo. Google's terms
restrict storing its content, and reviews are written to the local per-run evidence database, so
clear `backend/data/evidence.db` if that matters for your use.

