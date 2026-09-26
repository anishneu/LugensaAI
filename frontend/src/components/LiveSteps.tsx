import { useState } from "react";
import type { ResearchTraceStep } from "../types";

function stageLabel(step: ResearchTraceStep): string {
  return step.stage.replace(/_/g, " ");
}

/**
 * What the agent is doing right now, and nothing else: its latest trace step, streamed as it is recorded, as two plain lines with
 * no box of their own (the panel it sits in is the only container). The steps before it are one click away ("Show all"), as a timeline,
 * not on the screen by default: a growing list under a spinner is noise while the thing that matters is what it is doing this moment.
 * Every step is a real entry from the run's trace; none is invented.
 */
export function LiveSteps({ steps }: { steps: ResearchTraceStep[] }) {
  const [open, setOpen] = useState(false);
  if (steps.length === 0) return null;
  const current = steps[steps.length - 1];
  return (
    <div data-testid="research-steps" aria-live="polite" aria-label="What the agent is doing" className="flex w-full max-w-md flex-col items-center gap-2.5">
      <p className="m-0 flex flex-col items-center gap-0.5 text-center">
        <span className="flex items-center gap-2 text-[10.5px] font-semibold tracking-[0.1em] text-[var(--text-muted)] uppercase">
          <span className="relative flex h-1.5 w-1.5" aria-hidden="true">
            <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--accent)] opacity-60 motion-safe:animate-ping" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
          </span>
          {stageLabel(current)}
        </span>
        <span className="line-clamp-2 text-sm leading-snug text-[var(--text-h)]" dir="auto" title={current.description}>
          {current.description}
        </span>
      </p>

      {steps.length > 1 && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="rounded text-[11px] text-[var(--text-muted)] underline-offset-2 hover:text-[var(--text-h)] hover:underline focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none"
        >
          {open ? "Hide the steps" : `Show all ${steps.length} steps`}
        </button>
      )}

      {open && (
        <ol className="m-0 mt-1 flex max-h-56 w-full list-none flex-col gap-3 overflow-y-auto border-l border-[var(--border)] py-0.5 pr-1 pl-5 text-left">
          {steps.map((step, i) => (
            <li key={i} className="relative text-[12px] leading-snug text-[var(--text-muted)]" dir="auto">
              <span className="absolute top-1.5 -left-[25px] h-1.5 w-1.5 rounded-full bg-[var(--border)]" aria-hidden="true" />
              <span className="block text-[9.5px] font-semibold tracking-[0.08em] uppercase opacity-70">{stageLabel(step)}</span>
              {step.description}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
