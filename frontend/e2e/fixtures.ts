import type { Page, Route } from "@playwright/test";

/** Everything the UI asks the backend for is answered here, so the tests need no server. */

export const PLACE = {
  name: "Harvard Square",
  display_name: "Harvard Square, Cambridge, MA",
  category: "Tourist attraction",
  city: "Cambridge",
  region: "Massachusetts",
  country: "United States",
  latitude: 42.3736,
  longitude: -71.119,
  is_business: false,
  is_address: false,
};

const CAPABILITIES = {
  llm_provider: "ollama",
  llm_model: "qwen3:30b",
  live_search: true,
  live_geocoding: true,
  live_feed: true,
  estimated_seconds_min: 210,
  estimated_seconds_max: 660,
  first_run_warmup: false,
  translation: false,
  place_profile: false,
};

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "*",
  "access-control-allow-methods": "GET,POST,OPTIONS",
};

/** A live-feed item as the backend sends it. `minutesAgo` sets its real publication time. */
export function feedItem(id: string, title: string, minutesAgo: number, metadata: Record<string, string> = {}) {
  return {
    evidence_id: id,
    source_url: `https://news.example.org/${id}`,
    source_title: title,
    publisher: "Example Gazette",
    source_type: "news",
    retrieved_at: new Date().toISOString(),
    published_at: new Date(Date.now() - minutesAgo * 60_000).toISOString(),
    location_scope: "Cambridge",
    text: "",
    topic: "live_feed",
    metadata: { feed_kind: "news", feed_scope: "near", feed_place: "Harvard Square", feed_category: "News", ...metadata },
    relevance_score: null,
    quality_score: null,
    recency_days: null,
    image_url: null,
  };
}

/** A finished research answer, with just enough in it for every tab to have something to show. */
export function researchResult(question: string) {
  const trace = (description: string) => ({ stage: "retrieval", description, timestamp: new Date().toISOString(), details: {} });
  return {
    location: { name: "Harvard Square", city: "Cambridge", region: "Massachusetts", country: "United States", slug: "hs", latitude: 42.3736, longitude: -71.119, raw_query: "Harvard Square, Cambridge, MA", is_business: false },
    question,
    summary: "A lively, walkable area with plenty to do.",
    key_findings: ["It is easy to reach by subway."],
    details: "",
    recommendation: "Worth visiting.",
    topics: [{ topic_id: "transportation", reason: "asked about getting around", search_queries: [], preferred_source_types: [], expected_evidence: "", priority: "high", completion_criteria: "" }],
    claims: [{ claim_id: "c1", text: "The Red Line stops here.", claim_type: "fact", supporting_evidence_ids: ["e1"], contradicting_evidence_ids: [], status: "supported", limitations: [] }],
    evidence: [{ ...feedItem("e1", "Getting around Harvard Square", 60 * 24 * 5), topic: "transportation", metadata: {} }],
    limitations: ["Only one source was found for this topic."],
    research_trace: [trace("Resolved 'Harvard Square' to Harvard Square, Cambridge, MA"), trace("Accepted 1 evidence item(s) for 'transportation'")],
  };
}

interface MockOptions {
  /** What GET /api/live-feed returns. Empty by default. */
  feed?: ReturnType<typeof feedItem>[];
}

/** Answers every backend call the UI makes, blocks map tiles, and gives the test a hand-driven research stream:
 * `window.__sse.send(event, data)` and `window.__sse.close()` write to the response of POST /api/research/stream,
 * so a test can watch the page react between one step and the next. */
export async function mockBackend(page: Page, options: MockOptions = {}) {
  await page.route("**/tiles.openfreemap.org/**", (route) => route.abort());

  await page.addInitScript(() => {
    const realFetch = window.fetch.bind(window);
    const encoder = new TextEncoder();
    let controller: ReadableStreamDefaultController<Uint8Array> | null = null;
    const sse = {
      started: false,
      body: "",
      send(event: string, data: unknown) {
        controller?.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      },
      close() {
        controller?.close();
      },
    };
    (window as unknown as { __sse: typeof sse }).__sse = sse;
    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/research/stream")) {
        sse.started = true;
        sse.body = String(init?.body ?? "");
        const stream = new ReadableStream<Uint8Array>({ start: (c) => (controller = c) });
        return Promise.resolve(new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } }));
      }
      return realFetch(input, init);
    };
  });

  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", headers: CORS, body: JSON.stringify(body) });

  await page.route("**/api/**", (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/api/capabilities")) return json(route, CAPABILITIES);
    if (path.endsWith("/api/places/search")) return json(route, [PLACE]);
    if (path.endsWith("/api/places/live-feed") || path.endsWith("/api/live-feed")) return json(route, options.feed ?? []);
    if (path.endsWith("/api/places/profile")) return json(route, { detail: "No match" }, 404);
    if (path.endsWith("/api/places/nearby")) return json(route, { detail: "Live map lookups are disabled on this server." }, 503);
    if (path.endsWith("/api/places/popular")) return json(route, []);
    return json(route, { detail: "not mocked" }, 404);
  });
}

/** Opens the search page, picks Harvard Square from the (mocked) suggestions and waits for the workspace. */
export async function openWorkspace(page: Page) {
  await page.goto("/app");
  const search = page.getByPlaceholder(/Try/i).first();
  await search.fill("Harvard Square");
  await page.getByRole("option").first().click();
  await page.getByPlaceholder("Would this be a good place for…?").waitFor();
}
