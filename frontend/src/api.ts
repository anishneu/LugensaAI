import { parseSseBlock } from "./sse";
import type {
  ActiveLocation,
  Capabilities,
  Evidence,
  NearbyPlaces,
  PlaceProfile,
  PlaceCandidate,
  PopularPlace,
  ResearchRequest,
  ResearchResponse,
  ResearchTraceStep,
  TranslatedTexts,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ResearchApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ResearchApiError";
    this.status = status;
  }
}

/** How long a run is likely to take given what the backend has switched on.
 * Used only to set expectations next to a live elapsed timer — never returns
 * null-ish guesses, and the UI falls back to showing elapsed time alone if
 * this fails. */
export async function fetchCapabilities(): Promise<Capabilities | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/capabilities`);
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

/** The research request for a place and a question. A place with coordinates (picked from search, or already resolved) is sent
 * exactly as it is: re-resolving its name as text on the server could land on a different same-named place nearby. */
export function researchRequestFor(location: ActiveLocation, question: string): ResearchRequest {
  return {
    location: location.rawQuery,
    question,
    is_business: location.isBusiness,
    is_address: location.isAddress,
    latitude: location.latitude,
    longitude: location.longitude,
    city: location.city,
    region: location.region,
    country: location.country,
  };
}

export async function runResearch(request: ResearchRequest): Promise<ResearchResponse> {
  const response = await fetch(`${API_BASE_URL}/api/research`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail ?? `Request failed with status ${response.status}`;
    throw new ResearchApiError(detail, response.status);
  }

  return response.json();
}

/** The same research as `runResearch`, but reports each step the agent takes as it takes it (`onStep`), so the page can
 * show real progress during a run that lasts minutes. Resolves with the finished response, exactly as `runResearch`
 * does. Falls back to the plain request when the server has no streaming endpoint (an older backend). */
export async function runResearchStream(
  request: ResearchRequest,
  onStep: (step: ResearchTraceStep) => void,
): Promise<ResearchResponse> {
  const response = await fetch(`${API_BASE_URL}/api/research/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(request),
  });
  if (response.status === 404 || response.status === 405) return runResearch(request);
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => null);
    throw new ResearchApiError(body?.detail ?? `Request failed with status ${response.status}`, response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: ResearchResponse | null = null;

  const handle = (block: string) => {
    const parsed = parseSseBlock(block);
    if (!parsed) return;
    if (parsed.event === "step") onStep(JSON.parse(parsed.data) as ResearchTraceStep);
    else if (parsed.event === "result") result = JSON.parse(parsed.data) as ResearchResponse;
    else if (parsed.event === "error") {
      const failure = JSON.parse(parsed.data) as { status?: number; detail?: string };
      throw new ResearchApiError(failure.detail ?? "The research run failed.", failure.status ?? 500);
    }
  };

  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    for (let match = /\r?\n\r?\n/.exec(buffer); match; match = /\r?\n\r?\n/.exec(buffer)) {
      handle(buffer.slice(0, match.index));
      buffer = buffer.slice(match.index + match[0].length);
    }
    if (done) break;
  }
  if (buffer.trim()) handle(buffer);
  if (!result) throw new ResearchApiError("The research stream ended before an answer arrived.", 502);
  return result;
}

/** Live place search (Google when configured, else OpenStreetMap): any real
 * place, anywhere. Returns an empty array (never throws) on failure, so
 * autocomplete degrades quietly instead of surfacing an error banner. */
export async function searchPlaces(query: string, signal?: AbortSignal): Promise<PlaceCandidate[]> {
  if (query.trim().length < 3) return [];
  try {
    const response = await fetch(`${API_BASE_URL}/api/places/search?q=${encodeURIComponent(query)}`, { signal });
    if (!response.ok) return [];
    return await response.json();
  } catch {
    return [];
  }
}

/** Deterministic map data (OpenStreetMap) around a pin — not LLM output.
 * Throws on failure so the caller can say "unavailable" instead of implying
 * that nothing is nearby. */
export async function fetchNearby(latitude: number, longitude: number, signal?: AbortSignal): Promise<NearbyPlaces> {
  const response = await fetch(
    `${API_BASE_URL}/api/places/nearby?latitude=${latitude}&longitude=${longitude}`,
    { signal },
  );
  if (!response.ok) throw new ResearchApiError(`Nearby lookup failed (${response.status})`, response.status);
  return response.json();
}

/** Google Maps rating/reviews for one business. Rejects with a
 * ResearchApiError whose `status` says why: 503 = not configured on the
 * server, 404 = no matching listing, anything else = the lookup failed. */
export async function fetchPlaceProfile(
  name: string,
  latitude: number,
  longitude: number,
  city: string | null,
  signal?: AbortSignal,
): Promise<PlaceProfile> {
  const query = new URLSearchParams({ name, latitude: String(latitude), longitude: String(longitude) });
  if (city) query.set("city", city);
  const response = await fetch(`${API_BASE_URL}/api/places/profile?${query.toString()}`, { signal });
  if (!response.ok) throw new ResearchApiError(`Profile lookup failed (${response.status})`, response.status);
  return response.json();
}

/** Well-known places around a pin with Google's rating and review count. Rejects with a ResearchApiError: 503 means
 * Google isn't connected on the server. */
export async function fetchPopularPlaces(latitude: number, longitude: number, signal?: AbortSignal): Promise<PopularPlace[]> {
  const response = await fetch(`${API_BASE_URL}/api/places/popular?latitude=${latitude}&longitude=${longitude}`, { signal });
  if (!response.ok) throw new ResearchApiError(`Popular places lookup failed (${response.status})`, response.status);
  return response.json();
}

/** Machine translation of place names and addresses to English, in the language of where the pin is. */
export async function translateTexts(
  latitude: number,
  longitude: number,
  texts: string[],
  signal?: AbortSignal,
): Promise<TranslatedTexts> {
  const response = await fetch(`${API_BASE_URL}/api/places/translate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ latitude, longitude, texts }),
    signal,
  });
  if (!response.ok) throw new ResearchApiError(`Translation failed (${response.status})`, response.status);
  return response.json();
}

export interface LiveFeedParams {
  location: string;
  latitude?: number | null;
  longitude?: number | null;
  city?: string | null;
  region?: string | null;
  country?: string | null;
}

/** What's currently being said about this place — independent of any
 * research question asked in the chat. A real, billed Tavily search each
 * call; the caller is responsible for not polling this aggressively. */
/** `refresh` skips the server's one-hour cache and so costs real search credits: only for the refresh button. */
export async function fetchLiveFeed(params: LiveFeedParams, signal?: AbortSignal, refresh = false): Promise<Evidence[]> {
  const query = new URLSearchParams();
  query.set("location", params.location);
  if (params.latitude != null) query.set("latitude", String(params.latitude));
  if (params.longitude != null) query.set("longitude", String(params.longitude));
  if (params.city) query.set("city", params.city);
  if (params.region) query.set("region", params.region);
  if (params.country) query.set("country", params.country);
  if (refresh) query.set("refresh", "true");

  const response = await fetch(`${API_BASE_URL}/api/live-feed?${query.toString()}`, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ResearchApiError(body?.detail ?? `Live feed request failed (${response.status})`, response.status);
  }
  return response.json();
}
