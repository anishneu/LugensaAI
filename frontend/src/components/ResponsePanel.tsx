import { useEffect, useState } from "react";
import { fetchCapabilities } from "../api";
import type { Capabilities, QuerySession } from "../types";
import { cleanDisplayText } from "../textUtils";
import { ClaimsList } from "./ClaimsList";
import { CommunityVoices } from "./CommunityVoices";
import type { EvidenceSortMode } from "./EvidenceList";
import { EvidenceList } from "./EvidenceList";
import { ResearchTrace } from "./ResearchTrace";
import { VerdictBanner } from "./VerdictBanner";

interface ResponsePanelProps {
  session: QuerySession | null;
}

const VOICE_SOURCE_TYPES = new Set(["community_forum", "review_aggregator"]);

type TabId = "overview" | "community" | "claims" | "evidence" | "details";

function formatDuration(totalSeconds: number): string {
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
}

/** Elapsed time is the real measurement; the estimate beside it only sets
 * expectations, because run time swings from seconds to minutes depending on
 * whether a local model is doing the reasoning. Once elapsed passes the
 * estimate, the estimate is dropped rather than left contradicting the clock. */
function ResearchProgress({
  startedAt,
  capabilities,
}: {
  startedAt: string;
  capabilities: Capabilities | null;
}) {
  const [elapsed, setElapsed] = useState(() => Math.max(0, Math.round((Date.now() - new Date(startedAt).getTime()) / 1000)));

  useEffect(() => {
    const id = window.setInterval(() => {
      setElapsed(Math.max(0, Math.round((Date.now() - new Date(startedAt).getTime()) / 1000)));
    }, 1000);
    return () => window.clearInterval(id);
  }, [startedAt]);

  const overEstimate = capabilities != null && elapsed > capabilities.estimated_seconds_max;

  return (
    <div className="research-progress">
      <span className="research-elapsed">{formatDuration(elapsed)} elapsed</span>
      {capabilities && !overEstimate && (
        <span className="research-estimate">
          {" · "}usually {formatDuration(capabilities.estimated_seconds_min)}–
          {formatDuration(capabilities.estimated_seconds_max)}
        </span>
      )}
      {overEstimate && <span className="research-estimate">{" · "}taking longer than usual, still working</span>}
      {capabilities?.first_run_warmup && (
        <p className="research-progress-note">
          First question since the server started — it also loads the local search model, a one-time cost the
          next questions won't pay.
        </p>
      )}
      {capabilities?.llm_provider === "ollama" && (
        <p className="research-progress-note">
          Reasoning locally via Ollama ({capabilities.llm_model}) — speed depends on whether Ollama is using a GPU (a few minutes) or only the CPU (much longer).
        </p>
      )}
    </div>
  );
}

export function ResponsePanel({ session }: ResponsePanelProps) {
  const [sortMode, setSortMode] = useState<EvidenceSortMode>("relevance");
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);

  // Config-derived, so it's fetched once rather than per question.
  useEffect(() => {
    fetchCapabilities().then(setCapabilities);
  }, []);

  // Each question is its own little "document" — start back on Overview
  // rather than leaving the reader stranded on whatever tab the last
  // question happened to be showing.
  useEffect(() => {
    setActiveTab("overview");
  }, [session?.id]);

  if (!session) {
    return (
      <div className="response-panel empty">
        <p className="empty-state">Ask a question on the left to see the agent's research here.</p>
      </div>
    );
  }

  if (session.status === "loading") {
    return (
      <div className="response-panel loading">
        <div className="loading-spinner" />
        <p>Researching “{session.question}”…</p>
        <p className="loading-subtext">Planning topics, retrieving evidence, verifying claims.</p>
        <ResearchProgress startedAt={session.askedAt} capabilities={capabilities} />
      </div>
    );
  }

  if (session.status === "error" || !session.response) {
    return (
      <div className="response-panel error">
        <div className="error-banner">{session.error ?? "Something went wrong."}</div>
      </div>
    );
  }

  const response = session.response;
  const voiceCount = response.evidence.filter((e) => VOICE_SOURCE_TYPES.has(e.source_type)).length;

  const tabs: { id: TabId; label: string; count?: number }[] = [
    { id: "overview", label: "Overview" },
    { id: "community", label: "Community", count: voiceCount },
    { id: "claims", label: "Claims", count: response.claims.length },
    { id: "evidence", label: "Evidence", count: response.evidence.length },
    { id: "details", label: "Details" },
  ];

  return (
    <div className="response-panel">
      <p className="question-echo">“{response.question}”</p>

      <div className="response-tabs" role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            className={`response-tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
            {tab.count != null && <span className="response-tab-count">{tab.count}</span>}
          </button>
        ))}
      </div>

      <div className="response-tab-panel">
        {activeTab === "overview" && (
          <>
            <VerdictBanner response={response} />

            <section className="summary-section">
              <h3>Summary</h3>
              <p>{cleanDisplayText(response.summary)}</p>
            </section>

            {response.key_findings.length > 0 && (
              <section className="key-findings-section">
                <h3>Key findings</h3>
                <ul>
                  {response.key_findings.map((finding, i) => (
                    <li key={i}>{cleanDisplayText(finding)}</li>
                  ))}
                </ul>
              </section>
            )}

            {response.details && (
              <section className="details-section">
                <h3>Details</h3>
                {cleanDisplayText(response.details)
                  .split("\n\n")
                  .filter(Boolean)
                  .map((paragraph, i) => (
                    <p key={i}>{paragraph}</p>
                  ))}
              </section>
            )}

            <section className="topics-section">
              <h3>Research plan</h3>
              <div className="topics-chip-row">
                {response.topics.map((topic) => (
                  <div key={topic.topic_id} className={`topic-chip priority-${topic.priority}`} title={topic.reason}>
                    {topic.topic_id.replace(/_/g, " ")}
                  </div>
                ))}
              </div>
            </section>
          </>
        )}

        {activeTab === "community" && <CommunityVoices evidence={response.evidence} />}

        {activeTab === "claims" && (
          <section>
            <ClaimsList claims={response.claims} />
          </section>
        )}

        {activeTab === "evidence" && (
          <section>
            <div className="section-header-row">
              <h3>All evidence</h3>
              <div className="sort-toggle">
                <button
                  type="button"
                  className={sortMode === "relevance" ? "active" : ""}
                  onClick={() => setSortMode("relevance")}
                >
                  Most relevant
                </button>
                <button
                  type="button"
                  className={sortMode === "newest" ? "active" : ""}
                  onClick={() => setSortMode("newest")}
                >
                  Newest first
                </button>
              </div>
            </div>
            <p className="tab-hint">Tap a topic to expand its sources.</p>
            <EvidenceList evidence={response.evidence} sortMode={sortMode} />
          </section>
        )}

        {activeTab === "details" && (
          <>
            {response.limitations.length > 0 && (
              <section className="limitations-section">
                <h3>⚠ Known limitations</h3>
                <ul>
                  {response.limitations.map((limitation, i) => (
                    <li key={i}>{limitation}</li>
                  ))}
                </ul>
              </section>
            )}
            <ResearchTrace trace={response.research_trace} />
          </>
        )}
      </div>
    </div>
  );
}
