import { useMemo, useState } from "react";
import type { Evidence } from "../types";
import { cleanDisplayText, relativeTimeFrom } from "../textUtils";
import { SOURCE_TYPE_ICON } from "../sourceTypeIcon";

interface LiveFeedSidebarProps {
  evidence: Evidence[];
  locationName: string;
}

// Guards against stale localStorage history saved before the backend's
// location-relevance filter existed — never show something this weakly
// related to the topic it was retrieved for, regardless of when it was cached.
const MIN_FEED_RELEVANCE = 0.3;

function feedTimestamp(item: Evidence): number {
  return new Date(item.published_at ?? item.retrieved_at).getTime();
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

export function LiveFeedSidebar({ evidence, locationName }: LiveFeedSidebarProps) {
  const feed = useMemo(() => {
    const seen = new Set<string>();
    const deduped = evidence.filter((item) => {
      if (seen.has(item.evidence_id)) return false;
      seen.add(item.evidence_id);
      return item.relevance_score == null || item.relevance_score >= MIN_FEED_RELEVANCE;
    });
    return deduped.sort((a, b) => feedTimestamp(b) - feedTimestamp(a));
  }, [evidence]);

  return (
    <aside className="live-feed-sidebar">
      <div className="sidebar-heading">
        <h2>Live feed</h2>
        <p>Real sources the agent has surfaced for {locationName} so far, newest first.</p>
      </div>

      {feed.length === 0 ? (
        <p className="empty-note">Nothing yet — ask a question to start collecting evidence.</p>
      ) : (
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
                <span className="feed-item-topic">#{item.topic}</span>
              </div>
            </a>
          ))}
        </div>
      )}
    </aside>
  );
}
