import { useState } from "react";
import type { FormEvent } from "react";
import type { QuerySession } from "../types";
import { relativeTimeFrom } from "../textUtils";

const SUGGESTED_QUESTIONS = [
  "Is it a good place to visit as a tourist?",
  "What are the customer reviews and the food like?",
  "Is it safe, and easy to get around?",
];

interface ChatSidebarProps {
  sessions: QuerySession[];
  activeSessionId: string | null;
  onAsk: (question: string) => void;
  onSelectSession: (id: string) => void;
  busy: boolean;
  /** A question chosen elsewhere (the landing page), waiting in the box. It is never run for you. */
  initialDraft?: string;
}

const STATUS_ICON: Record<QuerySession["status"], string> = {
  loading: "⏳",
  done: "✓",
  error: "⚠",
};

const STATUS_BAR: Record<QuerySession["status"], string> = {
  loading: "bg-[var(--insufficient)]",
  done: "bg-[var(--supported)]",
  error: "bg-[var(--contradicted)]",
};

export function ChatSidebar({ sessions, activeSessionId, onAsk, onSelectSession, busy, initialDraft = "" }: ChatSidebarProps) {
  const [draft, setDraft] = useState(initialDraft);

  function submit(event: FormEvent) {
    event.preventDefault();
    const question = draft.trim();
    if (!question || busy) return;
    onAsk(question);
    setDraft("");
  }

  return (
    // On a desktop the column is as tall as the window and does not scroll: the map above takes what is left, and if the questions asked so
    // far outgrow this part, only their own list scrolls. (`max-h`: this part never squeezes the map below 180px.)
    <div className="flex min-w-0 shrink-0 flex-col gap-5 p-5 lg:min-h-0 lg:max-h-[calc(100%-180px)] [@media(max-height:760px)]:gap-3 [@media(max-height:760px)]:p-4">
      <div className="flex shrink-0 flex-col gap-1">
        <h2 className="m-0 flex items-center gap-1.5 text-[15px] font-bold text-[var(--text-h)]">💬 Ask the agent</h2>
        <p className="m-0 text-xs leading-relaxed text-[var(--text-muted)] [@media(max-height:760px)]:hidden">
          Each question runs a fresh research pass and is saved below.
        </p>
      </div>

      <form className="flex shrink-0 flex-col gap-2.5 rounded-2xl border border-[var(--border)] bg-[var(--bg)] p-3 shadow-sm" onSubmit={submit}>
        <textarea
          className="w-full resize-none rounded-lg border-none bg-transparent p-1 text-[13px] text-[var(--text)] outline-none placeholder:text-[var(--text-muted)]"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Would this be a good place for…?"
          rows={2}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              submit(e);
            }
          }}
        />
        <button
          type="submit"
          disabled={busy || !draft.trim()}
          className="self-end rounded-full bg-[var(--accent)] px-4.5 py-2 text-[13px] font-semibold text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-45"
        >
          {busy ? "Researching…" : "Ask →"}
        </button>
      </form>

      {sessions.length === 0 && (
        <div className="flex shrink-0 flex-col gap-1.5">
          <span className="text-[11px] font-medium text-[var(--text-muted)]">Try asking:</span>
          {SUGGESTED_QUESTIONS.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => onAsk(q)}
              disabled={busy}
              className="rounded-lg border border-[var(--border)] bg-[var(--bg)] px-2.5 py-2 text-left text-xs text-[var(--text)] transition-colors hover:border-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      <div className="flex min-h-0 flex-col gap-1.5 overflow-y-auto">
        {sessions
            .slice()
            .reverse()
            .map((session) => {
              const isActive = session.id === activeSessionId;
              return (
                <button
                  key={session.id}
                  type="button"
                  onClick={() => onSelectSession(session.id)}
                  className={`flex w-full items-start gap-2.5 rounded-xl border p-2.5 text-left transition-colors ${
                    isActive
                      ? "border-[var(--accent)] bg-[var(--bg)]"
                      : "border-transparent hover:border-[var(--border)] hover:bg-[var(--bg)]"
                  }`}
                >
                  <span className={`mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full ${STATUS_BAR[session.status]} ${session.status === "loading" ? "animate-pulse" : ""}`} />
                  <span className="flex min-w-0 flex-col gap-0.5">
                    <span className="line-clamp-2 text-[12.5px] text-[var(--text)]">
                      <span className="mr-1" aria-hidden="true">
                        {STATUS_ICON[session.status]}
                      </span>
                      {session.question}
                    </span>
                    <span className="text-[10.5px] text-[var(--text-muted)]">{relativeTimeFrom(session.askedAt)}</span>
                  </span>
                </button>
              );
            })}
      </div>
    </div>
  );
}
