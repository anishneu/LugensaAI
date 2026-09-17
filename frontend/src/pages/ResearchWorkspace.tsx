import { useEffect, useState } from "react";
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
  const [suggestions, setSuggestions] = useState<LocationSuggestion[]>([]);
  const [query, setQuery] = useState("");
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

  function handleSelectSuggestion(suggestion: LocationSuggestion) {
    selectLocation({
      rawQuery: suggestion.raw_query,
      displayName: `${suggestion.name}${suggestion.city ? `, ${suggestion.city}` : ""}`,
      city: suggestion.city,
      region: suggestion.region,
      latitude: suggestion.latitude,
      longitude: suggestion.longitude,
    });
  }

  function handleSubmitRawQuery(text: string) {
    selectLocation({
      rawQuery: text,
      displayName: text,
      city: null,
      region: null,
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
      const response = await runResearch({ location: location.rawQuery, question });
      setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, status: "done", response } : s)));

      if (location.latitude == null && response.location.latitude != null) {
        setLocation((prev) =>
          prev
            ? {
                ...prev,
                displayName: `${response.location.name}${response.location.city ? `, ${response.location.city}` : ""}`,
                city: response.location.city,
                region: response.location.region,
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
        onSelect={handleSelectSuggestion}
        onSubmit={handleSubmitRawQuery}
      />
    );
  }

  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? null;
  const allEvidence = sessions.flatMap((s) => s.response?.evidence ?? []);

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
        <LiveFeedSidebar evidence={allEvidence} locationName={location.displayName} />
      </div>
    </div>
  );
}
