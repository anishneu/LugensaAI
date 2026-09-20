import { useCallback, useEffect, useRef, useState } from "react";
import { fetchNearby } from "../api";
import type { ActiveLocation, NearbyPlaces } from "../types";

interface NearbyState {
  key: string;
  data: NearbyPlaces | null;
}

const WALKING_METERS_PER_MINUTE = 80;

function walkLabel(meters: number): string {
  const minutes = Math.max(1, Math.round(meters / WALKING_METERS_PER_MINUTE));
  return `${meters} m · ~${minutes} min walk`;
}

/** What's physically around the pin, straight from OpenStreetMap map data.
 * Deliberately separate from the agent's answer: these are listed features
 * with computed distances, not text an LLM summarized from web pages, so this
 * is the part of the page that can be trusted for "is there a bar / station /
 * pharmacy nearby". A single sliding row so it never pushes the answer down. */
export function NearbyCard({ location }: { location: ActiveLocation }) {
  const { latitude, longitude } = location;
  const key = latitude != null && longitude != null ? `${latitude},${longitude}` : "";
  const [state, setState] = useState<NearbyState | null>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ start: true, end: true });

  useEffect(() => {
    if (!key || latitude == null || longitude == null) return;
    const controller = new AbortController();
    fetchNearby(latitude, longitude, controller.signal)
      .then((data) => setState({ key, data }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ key, data: null });
      });
    return () => controller.abort();
  }, [key, latitude, longitude]);

  const settled = state?.key === key;
  const data = settled ? state.data : null;
  const groupCount = data?.groups.length ?? 0;

  const updateEdges = useCallback(() => {
    const el = trackRef.current;
    if (!el) return;
    setEdges({ start: el.scrollLeft <= 2, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 2 });
  }, []);

  // The arrows' enabled state depends on real overflow, so re-measure when
  // cards appear and when the window is resized.
  useEffect(() => {
    updateEdges();
    window.addEventListener("resize", updateEdges);
    return () => window.removeEventListener("resize", updateEdges);
  }, [groupCount, updateEdges]);

  function slide(direction: 1 | -1) {
    const el = trackRef.current;
    if (el) el.scrollBy({ left: direction * Math.max(el.clientWidth * 0.8, 240), behavior: "smooth" });
  }

  if (!key) return null;

  const arrow =
    "flex h-7 w-7 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--bg)] text-sm text-[var(--text)] transition-colors hover:border-[var(--accent)] disabled:cursor-default disabled:opacity-35 disabled:hover:border-[var(--border)]";

  return (
    <section className="mx-5 mt-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-alt)] px-4 py-3">
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-3">
          <h3 className="m-0 text-sm font-bold text-[var(--text-h)]">📍 Around this pin</h3>
          <span
            className="truncate text-[11px] text-[var(--text-muted)]"
            title="Ratings, reviews and opening hours aren't in map data. Those come from the web sources in the answer and are only as reliable as those sources."
          >
            OpenStreetMap · within {data?.radius_m ?? 600} m · not AI-generated
          </span>
        </div>
        {groupCount > 1 && (
          <div className="flex flex-shrink-0 gap-1.5">
            <button type="button" className={arrow} onClick={() => slide(-1)} disabled={edges.start} aria-label="Previous">
              ‹
            </button>
            <button type="button" className={arrow} onClick={() => slide(1)} disabled={edges.end} aria-label="Next">
              ›
            </button>
          </div>
        )}
      </div>

      {!settled && <p className="m-0 text-xs text-[var(--text-muted)]">Looking up what's nearby…</p>}

      {settled && !data && (
        <p className="m-0 text-xs text-[var(--text-muted)]">
          Map data is unavailable right now (the public OpenStreetMap server didn't respond). That doesn't mean
          nothing is nearby.
        </p>
      )}

      {data && data.groups.length === 0 && (
        <p className="m-0 text-xs text-[var(--text-muted)]">
          OpenStreetMap lists no named food, transit, shops, health, safety, or banking places within{" "}
          {data.radius_m} m of this pin. Map coverage varies by area, so this may reflect gaps in the map.
        </p>
      )}

      {data && data.groups.length > 0 && (
        <div
          ref={trackRef}
          onScroll={updateEdges}
          className="flex snap-x snap-mandatory gap-3 overflow-x-auto scroll-smooth pb-0.5"
        >
          {data.groups.map((group) => (
            <div
              key={group.label}
              className="w-60 flex-shrink-0 snap-start rounded-xl border border-[var(--border)] bg-[var(--bg)] p-3"
            >
              <div className="mb-1.5 flex items-baseline justify-between">
                <strong className="text-xs text-[var(--text-h)]">{group.label}</strong>
                <span className="text-[10.5px] text-[var(--text-muted)]">{group.total} listed</span>
              </div>
              <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
                {group.nearest.map((item) => (
                  <li key={`${item.name}-${item.distance_m}`} className="text-xs leading-snug text-[var(--text)]">
                    <span className="font-medium">{item.name}</span>
                    <span className="block text-[11px] text-[var(--text-muted)]">
                      {item.kind} · {walkLabel(item.distance_m)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
