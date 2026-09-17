import { useCallback, useEffect, useRef, useState } from "react";
import { fetchLiveFeed, ResearchApiError } from "../api";
import { cleanDisplayText, relativeTimeFrom } from "../textUtils";
import { SOURCE_TYPE_ICON } from "../sourceTypeIcon";
import type { ActiveLocation, Evidence } from "../types";

interface LiveFeedSidebarProps {
  location: ActiveLocation;
}

// A real, billed Tavily search runs on every fetch — auto-refresh stays
// infrequent by design; the manual button covers "I want it now."
const AUTO_REFRESH_MS = 3 * 60 * 1000;

function FeedMedia({ item }: { item: Evidence }) {
  const [failed, setFailed] = useState(false);
  if (item.image_url && !failed) {
    return (
      <img
        className="feed-thumbnail"
        src={item.image_url}
        alt={item.source_title}
        loading="lazy"
        onError={() => setFailed(true)}
      />
    );
  }
  return (
    <div className={`feed-thumbnail media-fallback type-${item.source_type}`} aria-hidden="true">
      {SOURCE_TYPE_ICON[item.source_type]}
    </div>
  );
}

export function LiveFeedSidebar({ location }: LiveFeedSidebarProps) {
  const [feed, setFeed] = useState<Evidence[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    fetchLiveFeed(
      {
        location: location.rawQuery,
        latitude: location.latitude,
        longitude: location.longitude,
        city: location.city,
        region: location.region,
        country: location.country,
      },
      controller.signal,
    )
      .then((items) => {
        setFeed(items);
        setUnavailable(items.length === 0);
        setLastUpdated(new Date().toISOString());
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(err instanceof ResearchApiError ? err.message : "Could not load the live feed.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, [location.rawQuery, location.latitude, location.longitude, location.city, location.region, location.country]);

  useEffect(() => {
    load();
    const interval = window.setInterval(load, AUTO_REFRESH_MS);
    return () => {
      window.clearInterval(interval);
      abortRef.current?.abort();
    };
  }, [load]);

  return (
    <aside className="live-feed-sidebar">
      <div className="sidebar-heading">
        <div className="feed-heading-row">
          <h2>Live feed</h2>
          <button type="button" className="feed-refresh-button" onClick={load} disabled={loading} title="Refresh now">
            {loading ? "⏳" : "↻"}
          </button>
        </div>
        <p>
          What's currently being said about {location.displayName} — real Reddit, news, and review activity from
          the last week, independent of the questions on the left.
        </p>
        {lastUpdated && <p className="feed-updated-at">Updated {relativeTimeFrom(lastUpdated)}</p>}
      </div>

      {error && <p className="empty-note">{error}</p>}

      {!error && unavailable && !loading && (
        <p className="empty-note">
          No live feed available — this needs a Tavily API key configured on the backend (`TAVILY_API_KEY`).
        </p>
      )}

      {!error && feed.length > 0 && (
        <div className="feed-items">
          {feed.map((item) => (
            <a key={item.evidence_id} href={item.source_url} target="_blank" rel="noreferrer" className="feed-item">
              <FeedMedia item={item} />
              <div className="feed-item-body">
                <div className="feed-item-meta">
                  <span className={`feed-source-type type-${item.source_type}`}>
                    {item.source_type.replace(/_/g, " ")}
                  </span>
                  <span className="feed-time">{relativeTimeFrom(item.published_at ?? item.retrieved_at)}</span>
                </div>
                <div className="feed-item-title">{item.source_title}</div>
                {item.publisher && <div className="feed-item-publisher">{item.publisher}</div>}
                <p className="feed-item-snippet">{cleanDisplayText(item.text)}</p>
              </div>
            </a>
          ))}
        </div>
      )}
    </aside>
  );
}
