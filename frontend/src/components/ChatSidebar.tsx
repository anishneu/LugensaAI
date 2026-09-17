import { useState } from "react";
import type { FormEvent } from "react";
import type { QuerySession } from "../types";
import { relativeTimeFrom } from "../textUtils";

const SUGGESTED_QUESTIONS = [
  "Would this be a good place for a college student?",
  "What's the nightlife like around here?",
  "Is it walkable and safe at night?",
];

interface ChatSidebarProps {
  sessions: QuerySession[];
  activeSessionId: string | null;
  onAsk: (question: string) => void;
  onSelectSession: (id: string) => void;
  busy: boolean;
}

const STATUS_ICON: Record<QuerySession["status"], string> = {
  loading: "⏳",
  done: "✓",
  error: "⚠",
};

export function ChatSidebar({ sessions, activeSessionId, onAsk, onSelectSession, busy }: ChatSidebarProps) {
  const [draft, setDraft] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    const question = draft.trim();
    if (!question || busy) return;
    onAsk(question);
    setDraft("");
  }

  return (
    <aside className="chat-sidebar">
      <div className="sidebar-heading">
        <h2>Ask the agent</h2>
        <p>Each question runs a fresh research pass and is saved below.</p>
      </div>

      <form className="chat-input-form" onSubmit={submit}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Would this be a good place for…?"
          rows={3}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              submit(e);
            }
          }}
        />
        <button type="submit" disabled={busy || !draft.trim()}>
          {busy ? "Researching…" : "Ask"}
        </button>
      </form>

      {sessions.length === 0 && (
        <div className="chat-suggestions">
          <span>Try asking:</span>
          {SUGGESTED_QUESTIONS.map((q) => (
            <button key={q} type="button" onClick={() => onAsk(q)} disabled={busy}>
              {q}
            </button>
          ))}
        </div>
      )}

      <div className="chat-history">
        {sessions
          .slice()
          .reverse()
          .map((session) => (
            <button
              key={session.id}
              type="button"
              className={`chat-history-item status-${session.status} ${
                session.id === activeSessionId ? "active" : ""
              }`}
              onClick={() => onSelectSession(session.id)}
            >
              <span className={`history-status-icon icon-${session.status}`}>{STATUS_ICON[session.status]}</span>
              <span className="history-text">
                <span className="history-question">{session.question}</span>
                <span className="history-time">{relativeTimeFrom(session.askedAt)}</span>
              </span>
            </button>
          ))}
      </div>
    </aside>
  );
}
