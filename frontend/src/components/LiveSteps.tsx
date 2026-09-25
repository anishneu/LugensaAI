import { CheckCircleIcon } from "@heroicons/react/24/outline";
import type { ResearchTraceStep } from "../types";

const VISIBLE_STEPS = 8;

/** What the agent is doing right now: its real trace steps, newest last, streamed while the run is going. */
export function LiveSteps({ steps }: { steps: ResearchTraceStep[] }) {
  if (steps.length === 0) return null;
  const shown = steps.slice(-VISIBLE_STEPS);
  const hidden = steps.length - shown.length;
  return (
    <ol
      data-testid="research-steps"
      aria-live="polite"
      aria-label="What the agent is doing"
      className="m-0 flex w-full max-w-lg list-none flex-col gap-2 p-0 text-left"
    >
      {hidden > 0 && <li className="text-[11px] text-[var(--text-muted)]">{hidden} earlier step{hidden === 1 ? "" : "s"}</li>}
      {shown.map((step, i) => {
        const current = i === shown.length - 1;
        return (
          <li key={hidden + i} className={`flex items-start gap-2.5 text-[13px] leading-snug ${current ? "text-[var(--text-h)]" : "text-[var(--text-muted)]"}`}>
            {current ? (
              <span className="mt-1.5 h-2 w-2 flex-shrink-0 animate-pulse rounded-full bg-[var(--accent)]" aria-hidden="true" />
            ) : (
              <CheckCircleIcon className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--supported)]" aria-hidden="true" />
            )}
            <span className="min-w-0">
              <span className="block text-[10px] font-semibold tracking-[0.08em] uppercase opacity-70">{step.stage.replace(/_/g, " ")}</span>
              <span dir="auto">{step.description}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
