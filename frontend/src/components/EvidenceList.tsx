import { useState } from "react";
import type { Evidence } from "../types";
import { cleanDisplayText } from "../textUtils";
import { TranslationNote } from "./TranslationNote";
import { SOURCE_TYPE_ICON } from "../sourceTypeIcon";

export type EvidenceSortMode = "relevance" | "newest";

interface EvidenceListProps {
  evidence: Evidence[];
  sortMode: EvidenceSortMode;
}

function sortedWithin(items: Evidence[], sortMode: EvidenceSortMode): Evidence[] {
  const copy = [...items];
  if (sortMode === "newest") {
    copy.sort((a, b) => {
      const at = new Date(a.published_at ?? a.retrieved_at).getTime();
      const bt = new Date(b.published_at ?? b.retrieved_at).getTime();
      return bt - at;
    });
  } else {
    copy.sort((a, b) => (b.relevance_score ?? 0) - (a.relevance_score ?? 0));
  }
  return copy;
}

function EvidenceMedia({ item }: { item: Evidence }) {
  const [failed, setFailed] = useState(false);
  if (item.image_url && !failed) {
    return (
      <img
        className="evidence-thumbnail"
        src={item.image_url}
        alt={item.source_title}
        loading="lazy"
        onError={() => setFailed(true)}
      />
    );
  }
  return (
    <div className={`evidence-thumbnail media-fallback type-${item.source_type}`} aria-hidden="true">
      {SOURCE_TYPE_ICON[item.source_type]}
    </div>
  );
}

function TopicGroup({ topic, items, sortMode }: { topic: string; items: Evidence[]; sortMode: EvidenceSortMode }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="evidence-topic-group">
      <button type="button" className="topic-group-toggle" onClick={() => setExpanded((v) => !v)}>
        <span className={`toggle-caret ${expanded ? "open" : ""}`}>▸</span>
        <h4>{topic.replace(/_/g, " ")}</h4>
        <span className="topic-group-count">{items.length}</span>
      </button>
      {expanded && (
        <div className="topic-group-body">
          {sortedWithin(items, sortMode).map((item) => (
            <div key={item.evidence_id} className="evidence-card">
              <EvidenceMedia item={item} />
              <div className="evidence-card-body">
                <div className="evidence-meta">
                  <span className={`source-type type-${item.source_type}`}>
                    {item.source_type.replace(/_/g, " ")}
                  </span>
                  {item.relevance_score != null && (
                    <span className="relevance-score" title="Relevance score assigned by the retriever">
                      ● {item.relevance_score.toFixed(2)}
                    </span>
                  )}
                  {item.recency_days != null && <span className="recency">{item.recency_days}d old</span>}
                </div>
                <a href={item.source_url} target="_blank" rel="noreferrer" className="evidence-title" dir="auto">
                  {item.source_title}
                </a>
                {item.publisher && <div className="evidence-publisher">{item.publisher}</div>}
                <TranslationNote item={item} />
                <p className="evidence-text" dir="auto">{cleanDisplayText(item.text)}</p>
                <a href={item.source_url} target="_blank" rel="noreferrer" className="evidence-source-link">
                  Read full source →
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function EvidenceList({ evidence, sortMode }: EvidenceListProps) {
  if (evidence.length === 0) {
    return <p className="empty-note">No evidence was collected.</p>;
  }

  const byTopic = new Map<string, Evidence[]>();
  for (const item of evidence) {
    const list = byTopic.get(item.topic) ?? [];
    list.push(item);
    byTopic.set(item.topic, list);
  }

  return (
    <div className="evidence-list">
      {[...byTopic.entries()].map(([topic, items]) => (
        <TopicGroup key={topic} topic={topic} items={items} sortMode={sortMode} />
      ))}
    </div>
  );
}
