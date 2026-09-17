import type { QuerySession } from "./types";

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
