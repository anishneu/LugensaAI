import type { ActiveLocation, QuerySession } from "./types";

const PREFIX = "lugensa:sessions:";

function keyFor(locationSlug: string): string {
  return `${PREFIX}${locationSlug}`;
}

/** Per-viewer convenience only — never the source of truth for anything the
 * backend already returns. Safe to fail silently (private browsing, quota,
 * a blocked storage API) since the app works fine with an empty history. */
export function loadSessions(locationSlug: string): QuerySession[] {
  try {
    const raw = localStorage.getItem(keyFor(locationSlug));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as QuerySession[];
    // A session stuck "loading" from a page refresh mid-request can never resolve.
    return parsed.map((s) => (s.status === "loading" ? { ...s, status: "error", error: "Interrupted." } : s));
  } catch {
    return [];
  }
}

export function saveSessions(locationSlug: string, sessions: QuerySession[]): void {
  try {
    localStorage.setItem(keyFor(locationSlug), JSON.stringify(sessions));
  } catch {
    // Ignore — history just won't persist this time.
  }
}

// ---- Saved places: a short list the viewer keeps, in this browser only.

const SAVED_KEY = "lugensa:saved-places";
const MAX_SAVED = 12;

export interface SavedPlace {
  savedAt: string;
  location: ActiveLocation;
}

/** One place, one key: its coordinates when it has them (two spellings of one spot are one place), else its text. */
export function placeKey(location: ActiveLocation): string {
  return location.latitude != null && location.longitude != null
    ? `${location.latitude.toFixed(4)},${location.longitude.toFixed(4)}`
    : location.rawQuery.trim().toLowerCase();
}

export function loadSavedPlaces(): SavedPlace[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(SAVED_KEY) ?? "[]") as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (entry): entry is SavedPlace =>
        typeof entry === "object" && entry !== null && typeof (entry as SavedPlace).location?.rawQuery === "string",
    );
  } catch {
    return [];
  }
}

function writeSavedPlaces(list: SavedPlace[]): SavedPlace[] {
  try {
    localStorage.setItem(SAVED_KEY, JSON.stringify(list));
  } catch {
    // Ignore: the list just will not survive this time.
  }
  return list;
}

/** Saves the place, or removes it if it is already saved. Returns the new list, newest first. */
export function toggleSavedPlace(location: ActiveLocation): SavedPlace[] {
  const list = loadSavedPlaces();
  const key = placeKey(location);
  if (list.some((entry) => placeKey(entry.location) === key)) return removeSavedPlace(key);
  return writeSavedPlaces([{ savedAt: new Date().toISOString(), location }, ...list].slice(0, MAX_SAVED));
}

export function removeSavedPlace(key: string): SavedPlace[] {
  return writeSavedPlaces(loadSavedPlaces().filter((entry) => placeKey(entry.location) !== key));
}
