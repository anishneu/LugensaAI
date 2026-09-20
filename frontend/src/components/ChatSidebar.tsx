import { useState } from "react";
import type { FormEvent } from "react";
import { AnimatePresence, motion } from "framer-motion";
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
    <aside className="flex max-h-80 min-h-0 min-w-0 flex-col gap-5 overflow-y-auto border-b border-[var(--border)] bg-[var(--bg-alt)] p-5 lg:max-h-none lg:border-r lg:border-b-0">
      <div className="flex flex-col gap-1">
        <h2 className="m-0 flex items-center gap-1.5 text-[15px] font-bold text-[var(--text-h)]">💬 Ask the agent</h2>
        <p className="m-0 text-xs leading-relaxed text-[var(--text-muted)]">
          Each question runs a fresh research pass and is saved below.
        </p>
      </div>

      <form className="flex flex-col gap-2.5 rounded-2xl border border-[var(--border)] bg-[var(--bg)] p-3 shadow-sm" onSubmit={submit}>
        <textarea
          className="w-full resize-none rounded-lg border-none bg-transparent p-1 text-[13px] text-[var(--text)] outline-none placeholder:text-[var(--text-muted)]"
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
        <motion.button
          type="submit"
          disabled={busy || !draft.trim()}
          whileTap={{ scale: 0.96 }}
          className="self-end rounded-full bg-[var(--accent)] px-4.5 py-2 text-[13px] font-semibold text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-45"
        >
          {busy ? "Researching…" : "Ask →"}
        </motion.button>
      </form>

      {sessions.length === 0 && (
        <div className="flex flex-col gap-1.5">
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

      <div className="flex flex-col gap-1.5 overflow-y-auto">
        <AnimatePresence initial={false}>
          {sessions
            .slice()
            .reverse()
            .map((session) => {
              const isActive = session.id === activeSessionId;
              return (
                <motion.button
                  key={session.id}
                  type="button"
                  layout
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
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
                </motion.button>
              );
            })}
        </AnimatePresence>
      </div>
    </aside>
  );
}
