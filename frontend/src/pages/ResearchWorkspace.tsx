import { useEffect, useState } from "react";
import { useLocation as useRouterLocation } from "react-router-dom";
import { fetchLocationSuggestions, ResearchApiError, runResearch } from "../api";
import { ChatSidebar } from "../components/ChatSidebar";
import { LiveFeedSidebar } from "../components/LiveFeedSidebar";
import { ResponsePanel } from "../components/ResponsePanel";
import { SearchHero } from "../components/SearchHero";
import { WorkspaceHeader } from "../components/WorkspaceHeader";
import { loadSessions, saveSessions } from "../storage";
import type { ActiveLocation, LocationSuggestion, QuerySession } from "../types";
import "./ResearchWorkspace.css";

function normalizeKey(rawQuery: string): string {
  return rawQuery.trim().toLowerCase();
}

export function ResearchWorkspace() {
  // The landing page's "try it on" chips navigate here with a location
  // string pre-seeded via router state — this only pre-fills the search
  // box, it never auto-submits, so the user always picks the real result.
  const routerLocation = useRouterLocation();
  const seedQuery = (routerLocation.state as { seedQuery?: string } | null)?.seedQuery ?? "";

  const [suggestions, setSuggestions] = useState<LocationSuggestion[]>([]);
  const [query, setQuery] = useState(seedQuery);
  const [location, setLocation] = useState<ActiveLocation | null>(null);
  const [sessions, setSessions] = useState<QuerySession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  useEffect(() => {
    fetchLocationSuggestions()
      .then(setSuggestions)
      .catch(() => setSuggestions([])); // Autocomplete is a convenience, not required for the app to work.
  }, []);

  useEffect(() => {
    if (!location) return;
    const loaded = loadSessions(normalizeKey(location.rawQuery));
    setSessions(loaded);
    setActiveSessionId(loaded.length > 0 ? loaded[loaded.length - 1].id : null);
  }, [location?.rawQuery]);

  useEffect(() => {
    if (!location) return;
    saveSessions(normalizeKey(location.rawQuery), sessions);
  }, [location?.rawQuery, sessions]);

  function selectLocation(next: ActiveLocation) {
    setLocation(next);
    setQuery("");
  }

  function handleSubmitRawQuery(text: string) {
    selectLocation({
      rawQuery: text,
      displayName: text,
      city: null,
      region: null,
      country: null,
      latitude: null,
      longitude: null,
    });
  }

  const busy = sessions.some((s) => s.status === "loading");

  async function handleAsk(question: string) {
    if (!location) return;
    const id = crypto.randomUUID();
    const newSession: QuerySession = {
      id,
      question,
      askedAt: new Date().toISOString(),
      status: "loading",
      response: null,
      error: null,
    };
    setSessions((prev) => [...prev, newSession]);
    setActiveSessionId(id);

    try {
      // A location with known coordinates (picked from live search, or
      // already resolved by a previous question) is passed through exactly
      // as-is — re-resolving its name as text server-side could land on a
      // different same-named place nearby.
      const response = await runResearch({
        location: location.rawQuery,
        question,
        latitude: location.latitude,
        longitude: location.longitude,
        city: location.city,
        region: location.region,
        country: location.country,
      });
      setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, status: "done", response } : s)));

      if (location.latitude == null && response.location.latitude != null) {
        setLocation((prev) =>
          prev
            ? {
                ...prev,
                displayName: `${response.location.name}${response.location.city ? `, ${response.location.city}` : ""}`,
                city: response.location.city,
                region: response.location.region,
                country: response.location.country,
                latitude: response.location.latitude,
                longitude: response.location.longitude,
              }
            : prev,
        );
      }
    } catch (err) {
      const message =
        err instanceof ResearchApiError ? err.message : "Could not reach the research API. Is the backend running?";
      setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, status: "error", error: message } : s)));
    }
  }

  if (!location) {
    return (
      <SearchHero
        query={query}
        onQueryChange={setQuery}
        suggestions={suggestions}
        onSelect={selectLocation}
        onSubmit={handleSubmitRawQuery}
      />
    );
  }

  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? null;

  return (
    <div className="workspace">
      <WorkspaceHeader location={location} onChangeLocation={() => setLocation(null)} />
      <div className="workspace-body">
        <ChatSidebar
          sessions={sessions}
          activeSessionId={activeSessionId}
          onAsk={handleAsk}
          onSelectSession={setActiveSessionId}
          busy={busy}
        />
        <main className="workspace-center">
          <ResponsePanel session={activeSession} />
        </main>
        <LiveFeedSidebar location={location} />
      </div>
    </div>
  );
}
