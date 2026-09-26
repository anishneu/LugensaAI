import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useLocation as useRouterLocation } from "react-router-dom";
import { ResearchApiError, researchRequestFor, runResearchStream, searchPlaces } from "../api";
import { ComparePlaces } from "../components/ComparePlaces";
import { ChatSidebar } from "../components/ChatSidebar";
import { PlacePanel } from "../components/place/PlacePanel";
import { LiveFeedSidebar } from "../components/LiveFeedSidebar";
import { ResponsePanel } from "../components/ResponsePanel";
import { SearchHero } from "../components/SearchHero";
import { TopNav } from "../components/TopNav";
import { loadSavedPlaces, loadSessions, placeKey, removeSavedPlace, saveSessions, toggleSavedPlace } from "../storage";
import type { ActiveLocation, QuerySession } from "../types";

// MapLibre is large, so the map loads in its own chunk after the page is usable.
const MapPanel = lazy(() => import("../components/MapPanel"));

function normalizeKey(rawQuery: string): string {
  return rawQuery.trim().toLowerCase();
}

export function ResearchWorkspace() {
  // The landing page hands over a question chosen there through router state; it is put in the question box but never
  // run for you. (`location` and `submitQuery` are still read, for links that carry a place.)
  const routerLocation = useRouterLocation();
  const handoff = (routerLocation.state as { location?: ActiveLocation; submitQuery?: string; question?: string | null } | null) ?? {};

  const [query, setQuery] = useState("");
  const [location, setLocation] = useState<ActiveLocation | null>(handoff.location ?? null);
  const [sessions, setSessions] = useState<QuerySession[]>([]);
  const [saved, setSaved] = useState(loadSavedPlaces);
  const [compareOpen, setCompareOpen] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  // Text typed on the landing page is resolved once on arrival (a ref, because StrictMode runs effects twice).
  const handedOver = useRef(false);
  useEffect(() => {
    if (handedOver.current || !handoff.submitQuery) return;
    handedOver.current = true;
    handleSubmitRawQuery(handoff.submitQuery);
  }, []);

  // Saved questions are loaded when a place opens, and written back only once they have been loaded for that place.
  // Writing on every render wrote the empty starting list over the saved one whenever effects ran twice (React's dev
  // mode does), which lost every saved question on a reload.
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  useEffect(() => {
    if (!location) return;
    const key = normalizeKey(location.rawQuery);
    const loaded = loadSessions(key);
    setSessions(loaded);
    setActiveSessionId(loaded.length > 0 ? loaded[loaded.length - 1].id : null);
    setLoadedFor(key);
  }, [location?.rawQuery]);

  useEffect(() => {
    if (!location) return;
    const key = normalizeKey(location.rawQuery);
    if (loadedFor === key) saveSessions(key, sessions);
  }, [location?.rawQuery, sessions, loadedFor]);

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
      isBusiness: false,
      isAddress: false,
    });

    // Geocode right away so the map shows the right place immediately, rather
    // than sitting empty until the first (slow) research answer comes back.
    searchPlaces(text).then((places) => {
      const top = places[0];
      if (!top) return;
      setLocation((prev) =>
        prev && prev.rawQuery === text && prev.latitude == null
          ? {
              ...prev,
              displayName: `${top.name}${top.city ? `, ${top.city}` : ""}`,
              city: top.city,
              region: top.region,
              country: top.country,
              latitude: top.latitude,
              longitude: top.longitude,
              isBusiness: top.is_business,
              isAddress: top.is_address,
              googlePlaceId: top.google_place_id ?? null,
            }
          : prev,
      );
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
      const response = await runResearchStream(
        researchRequestFor(location, question),
        // Each step the agent takes is shown while the run is still going.
        (step) => setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, steps: [...(s.steps ?? []), step] } : s))),
      );
      setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, status: "done", steps: undefined, response } : s)));

      // Refine the location from the answer when it was unresolved, or when the backend matched a street
      // address to the business standing at it (so the Google card and the header show that business).
      const matchedBusiness = response.location.is_business && !location.isBusiness;
      if ((location.latitude == null && response.location.latitude != null) || matchedBusiness) {
        setLocation((prev) =>
          prev
            ? {
                ...prev,
                displayName: `${response.location.name}${response.location.city ? `, ${response.location.city}` : ""}`,
                city: response.location.city,
                region: response.location.region,
                country: response.location.country,
                isBusiness: response.location.is_business,
                isAddress: false,
                googlePlaceId: null, // the pin moved to the place the answer resolved, so the picked result's id no longer applies
                latitude: response.location.latitude,
                longitude: response.location.longitude,
              }
            : prev,
        );
      }
    } catch (err) {
      const message =
        err instanceof ResearchApiError ? err.message : "Could not reach the research API. Is the backend running?";
      setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, status: "error", steps: undefined, error: message } : s)));
    }
  }

  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? null;

  if (!location) {
    return <SearchHero
        query={query}
        onQueryChange={setQuery}
        onSelect={selectLocation}
        onSubmit={handleSubmitRawQuery}
        pendingQuestion={handoff.question}
        saved={saved}
        onRemoveSaved={(key) => setSaved(removeSavedPlace(key))}
      />;
  }

  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] lg:h-screen">
          <TopNav
            location={location}
            onChangeLocation={() => setLocation(null)}
            saved={saved}
            isSaved={saved.some((entry) => placeKey(entry.location) === placeKey(location))}
            onToggleSaved={() => setSaved(toggleSavedPlace(location))}
            onOpenSaved={selectLocation}
            onRemoveSaved={(key) => setSaved(removeSavedPlace(key))}
            onCompare={() => setCompareOpen(true)}
          />
          <ComparePlaces
            key={placeKey(location)}
            open={compareOpen}
            onClose={() => setCompareOpen(false)}
            place={location}
            defaultQuestion={activeSession?.question ?? ""}
          />
          <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[264px_minmax(0,1fr)_288px] xl:grid-cols-[340px_minmax(0,1fr)_340px]">
            {/* Left: the pin on a zoomed-in map, and where you ask. */}
            <aside className="flex min-h-0 flex-col border-b border-[var(--border)] bg-[var(--bg-alt)] lg:overflow-hidden lg:border-r lg:border-b-0">
              <Suspense fallback={<div className="h-64 w-full animate-pulse bg-[var(--bg)] lg:h-auto lg:min-h-[180px] lg:flex-1" />}>
                <MapPanel location={location} />
              </Suspense>
              <ChatSidebar
                initialDraft={handoff.question ?? ""}
                sessions={sessions}
                activeSessionId={activeSessionId}
                onAsk={handleAsk}
                onSelectSession={setActiveSessionId}
                busy={busy}
              />
            </aside>

            {/* Centre: the answer. */}
            <main className="min-h-0 min-w-0 pb-8 lg:overflow-y-auto">
              <PlacePanel location={location} />
              <ResponsePanel session={activeSession} />
            </main>

            {/* Right: what's being said about the place lately. */}
            <aside className="min-h-0 border-t border-[var(--border)] lg:overflow-y-auto lg:border-t-0 lg:border-l">
              <LiveFeedSidebar location={location} />
            </aside>
          </div>
    </div>
  );
}
