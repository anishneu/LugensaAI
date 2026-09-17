import { useCallback, useEffect, useRef, useState } from "react";
import { fetchLiveFeed, ResearchApiError } from "../api";
import { cleanDisplayText, formatFeedTimestamp, relativeTimeFrom } from "../textUtils";
import { SOURCE_TYPE_ICON } from "../sourceTypeIcon";
import type { ActiveLocation, Evidence } from "../types";

interface LiveFeedSidebarProps {
  location: ActiveLocation;
}

// A real, billed Tavily search runs on every fetch — auto-refresh stays
// infrequent by design; the manual button covers "I want it now."
const AUTO_REFRESH_MS = 3 * 60 * 1000;
const PAGE_SIZE = 5;
const MAX_PAGES = 3;

function regionLabel(location: ActiveLocation): string {
  return [location.city, location.region].filter(Boolean).join(", ") || location.displayName;
}

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
  const [page, setPage] = useState(1);
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
        setPage(1);
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

  const totalPages = Math.min(Math.ceil(feed.length / PAGE_SIZE) || 1, MAX_PAGES);
  const pageItems = feed.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

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
          What's happening recently around {regionLabel(location)} — real Reddit, news, and review activity from
          the last week, independent of the questions on the left and not limited to {location.displayName} itself.
        </p>
        {lastUpdated && (
          <p className="feed-updated-at">{loading ? "Refreshing…" : `Updated ${relativeTimeFrom(lastUpdated)}`}</p>
        )}
      </div>

      {error && <p className="empty-note">{error}</p>}

      {!error && unavailable && !loading && (
        <p className="empty-note">
          No live feed available — this needs a Tavily API key configured on the backend (`TAVILY_API_KEY`).
        </p>
      )}

      {!error && pageItems.length > 0 && (
        <>
          <div className="feed-items">
            {pageItems.map((item) => (
              <a key={item.evidence_id} href={item.source_url} target="_blank" rel="noreferrer" className="feed-item">
                <FeedMedia item={item} />
                <div className="feed-item-body">
                  <div className="feed-item-meta">
                    <span className={`feed-source-type type-${item.source_type}`}>
                      {item.source_type.replace(/_/g, " ")}
                    </span>
                    <span className="feed-time">{formatFeedTimestamp(item.published_at, item.retrieved_at)}</span>
                  </div>
                  <div className="feed-item-title">{item.source_title}</div>
                  <p className="feed-item-snippet">{cleanDisplayText(item.text)}</p>
                  <div className="feed-item-footer">
                    <span className="feed-item-location">📍 {item.location_scope}</span>
                    {item.publisher && <span className="feed-item-publisher">{item.publisher}</span>}
                  </div>
                </div>
              </a>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="feed-pagination">
              <button type="button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
                ‹
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map((n) => (
                <button
                  key={n}
                  type="button"
                  className={n === page ? "active" : ""}
                  onClick={() => setPage(n)}
                >
                  {n}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
              >
                ›
              </button>
            </div>
          )}
        </>
      )}
    </aside>
  );
}
