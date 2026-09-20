import { useState } from "react";
import type { Evidence } from "../types";
import { absoluteTimeFrom, cleanDisplayText, formatFeedTimestamp } from "../textUtils";
import { TranslationNote } from "./TranslationNote";
import { SOURCE_TYPE_ICON } from "../sourceTypeIcon";

interface CommunityVoicesProps {
  evidence: Evidence[];
}

const VOICE_SOURCE_TYPES = new Set(["community_forum", "review_aggregator"]);
const INITIAL_VISIBLE = 4;

function VoiceMedia({ item }: { item: Evidence }) {
  const [failed, setFailed] = useState(false);
  if (item.image_url && !failed) {
    return (
      <img
        className="voice-thumbnail"
        src={item.image_url}
        alt={item.source_title}
        loading="lazy"
        onError={() => setFailed(true)}
      />
    );
  }
  return (
    <div className={`voice-thumbnail media-fallback type-${item.source_type}`} aria-hidden="true">
      {SOURCE_TYPE_ICON[item.source_type]}
    </div>
  );
}

export function CommunityVoices({ evidence }: CommunityVoicesProps) {
  const [showAll, setShowAll] = useState(false);

  const voices = evidence
    .filter((e) => VOICE_SOURCE_TYPES.has(e.source_type))
    .sort((a, b) => new Date(b.published_at ?? b.retrieved_at).getTime() - new Date(a.published_at ?? a.retrieved_at).getTime());

  const visible = showAll ? voices : voices.slice(0, INITIAL_VISIBLE);
  const remaining = voices.length - visible.length;

  return (
    <section className="community-voices">
      <h3>💬 Community voices</h3>
      <p className="voices-subtitle">
        Real comments and reviews from forums and review sites — including mixed or negative opinions and
        recent incident reports. Shown for awareness, not fact-checked one by one: read the source before
        treating any single comment as settled fact.
      </p>

      {voices.length === 0 ? (
        <p className="empty-note">No forum or review commentary was found for this question.</p>
      ) : (
        <>
          <div className="voice-cards">
            {visible.map((item) => (
              <div key={item.evidence_id} className="voice-card">
                <VoiceMedia item={item} />
                <div className="voice-card-body">
                  <div className="voice-meta">
                    <span className={`source-type type-${item.source_type}`}>
                      {item.source_type.replace(/_/g, " ")}
                    </span>
                    <span className="voice-time" title={item.published_at ?? undefined}>
                      {formatFeedTimestamp(item.published_at, item.retrieved_at)}
                    </span>
                  </div>
                  <TranslationNote item={item} />
                  <p className="voice-text" dir="auto">“{cleanDisplayText(item.text)}”</p>
                  {item.published_at && (
                    <div className="voice-posted">🕒 Posted {absoluteTimeFrom(item.published_at)}</div>
                  )}
                  <div className="voice-footer">
                    {item.publisher && <span className="voice-publisher">{item.publisher}</span>}
                    <a href={item.source_url} target="_blank" rel="noreferrer">
                      View original →
                    </a>
                  </div>
                </div>
              </div>
            ))}
          </div>
          {remaining > 0 && (
            <button type="button" className="show-more-voices" onClick={() => setShowAll(true)}>
              Show {remaining} more
            </button>
          )}
        </>
      )}
    </section>
  );
}
