import type { LocationSuggestion, ResearchRequest, ResearchResponse } from "./types";

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
