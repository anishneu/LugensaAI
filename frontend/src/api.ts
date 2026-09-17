import type { Evidence, LocationSuggestion, PlaceCandidate, ResearchRequest, ResearchResponse } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ResearchApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ResearchApiError";
    this.status = status;
  }
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

export async function fetchLocationSuggestions(): Promise<LocationSuggestion[]> {
  const response = await fetch(`${API_BASE_URL}/api/locations`);
  if (!response.ok) {
    throw new ResearchApiError(`Could not load location suggestions (${response.status})`, response.status);
  }
  return response.json();
}

/** Live point-of-interest search (e.g. every Starbucks near "Cambridge, MA") —
 * any real place, not just the two demo neighborhoods. Returns an empty
 * array (never throws) on failure — autocomplete should degrade quietly to
 * the static suggestions rather than surface an error banner. */
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
export async function fetchLiveFeed(params: LiveFeedParams, signal?: AbortSignal): Promise<Evidence[]> {
  const query = new URLSearchParams();
  query.set("location", params.location);
  if (params.latitude != null) query.set("latitude", String(params.latitude));
  if (params.longitude != null) query.set("longitude", String(params.longitude));
  if (params.city) query.set("city", params.city);
  if (params.region) query.set("region", params.region);
  if (params.country) query.set("country", params.country);

  const response = await fetch(`${API_BASE_URL}/api/live-feed?${query.toString()}`, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ResearchApiError(body?.detail ?? `Live feed request failed (${response.status})`, response.status);
  }
  return response.json();
}
