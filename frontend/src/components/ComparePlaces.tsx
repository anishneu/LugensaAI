import { useRef, useState } from "react";
import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from "@headlessui/react";
import { ArrowDownTrayIcon, ExclamationTriangleIcon, PrinterIcon, XMarkIcon } from "@heroicons/react/24/outline";
import { ResearchApiError, researchRequestFor, runResearchStream } from "../api";
import { downloadText, printHtml } from "../download";
import { buildComparisonHtml, buildComparisonMarkdown, buildReportMarkdown, comparisonFileName, compareRows, placeTitle, reportFileName } from "../report";
import { cleanDisplayText } from "../textUtils";
import type { ActiveLocation, ResearchResponse, ResearchTraceStep } from "../types";
import { LiveSteps } from "./LiveSteps";
import { LocationSearchInput } from "./LocationSearchInput";
import { VerdictBanner } from "./VerdictBanner";

interface ComparePlacesProps {
  open: boolean;
  onClose: () => void;
  /** The place open in the workspace: the first of the two. */
  place: ActiveLocation;
  /** The last question asked here, offered as the one to compare on. */
  defaultQuestion: string;
}

interface Run {
  status: "waiting" | "loading" | "done" | "error";
  steps: ResearchTraceStep[];
  response?: ResearchResponse;
  error?: string;
}

const IDLE: [Run, Run] = [
  { status: "waiting", steps: [] },
  { status: "waiting", steps: [] },
];

const button =
  "flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--bg-alt)] px-4 py-2 text-[13px] font-medium text-[var(--text-h)] transition-colors hover:border-[var(--accent)] focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50";

function Column({ title, run, waitingFor }: { title: string; run: Run; waitingFor: string | null }) {
  return (
    <section className="flex min-w-0 flex-col gap-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-alt)] p-5" aria-label={title}>
      <h3 className="m-0 truncate text-base font-bold text-[var(--text-h)]" dir="auto" title={title}>
        {title}
      </h3>
      {run.status === "waiting" && <p className="m-0 text-sm text-[var(--text-muted)]">{waitingFor ? `Waiting for ${waitingFor} to finish.` : "Waiting to start."}</p>}
      {run.status === "loading" && (
        <>
          <div className="flex items-center gap-3 text-sm text-[var(--text-muted)]">
            <span className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--accent)]" aria-hidden="true" />
            Researching…
          </div>
          <LiveSteps steps={run.steps} />
        </>
      )}
      {run.status === "error" && (
        <div className="flex items-start gap-2.5 rounded-xl border border-red-500/40 bg-red-500/[0.08] p-3 text-sm text-[var(--contradicted)]">
          <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
          {run.error ?? "Something went wrong."}
        </div>
      )}
      {run.status === "done" && run.response && <Result response={run.response} />}
    </section>
  );
}

function Result({ response }: { response: ResearchResponse }) {
  return (
    <div className="flex flex-col gap-4">
      <VerdictBanner response={response} />
      <div>
        <h4 className="m-0 mb-1.5 text-[11px] font-bold tracking-[0.1em] text-[var(--text-muted)] uppercase">Summary</h4>
        <p className="m-0 text-sm leading-relaxed text-[var(--text)]" dir="auto">
          {cleanDisplayText(response.summary)}
        </p>
      </div>
      {response.key_findings.length > 0 && (
        <div>
          <h4 className="m-0 mb-1.5 text-[11px] font-bold tracking-[0.1em] text-[var(--text-muted)] uppercase">Key findings</h4>
          <ul className="m-0 flex list-disc flex-col gap-1.5 pl-5 text-sm leading-relaxed text-[var(--text)]">
            {response.key_findings.map((finding, i) => (
              <li key={i} dir="auto">
                {cleanDisplayText(finding)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {response.limitations.length > 0 && (
        <p className="m-0 text-xs text-[var(--text-muted)]">
          {response.limitations.length} known limitation{response.limitations.length === 1 ? "" : "s"}: {cleanDisplayText(response.limitations[0]).slice(0, 160)}
          {response.limitations.length > 1 || response.limitations[0].length > 160 ? "… (all of them are in the downloaded report)" : ""}
        </p>
      )}
      <button
        type="button"
        onClick={() => downloadText(reportFileName(response), buildReportMarkdown(response))}
        className={`${button} w-fit`}
      >
        <ArrowDownTrayIcon className="h-4 w-4" aria-hidden="true" />
        Download this report
      </button>
    </div>
  );
}

/** Two places, one question: the same research run once for each (one after the other, since the local model is one machine),
 * shown side by side. It counts what each run found and shows each answer; it never says which place is better, because nothing
 * in the sources decides that. */
export function ComparePlaces({ open, onClose, place, defaultQuestion }: ComparePlacesProps) {
  const [other, setOther] = useState<ActiveLocation | null>(null);
  const [query, setQuery] = useState("");
  // What the viewer typed; until they type, the last question asked in the workspace is offered.
  const [typed, setTyped] = useState<string | null>(null);
  const question = typed ?? defaultQuestion;
  const [runs, setRuns] = useState<[Run, Run]>(IDLE);
  const [phase, setPhase] = useState<"form" | "running" | "done">("form");
  const token = useRef(0);

  const nameA = place.displayName;
  const nameB = other?.displayName ?? "";
  const update = (index: 0 | 1, change: (run: Run) => Run) =>
    setRuns((prev) => (index === 0 ? [change(prev[0]), prev[1]] : [prev[0], change(prev[1])]));

  async function start() {
    if (!other || !question.trim()) return;
    const mine = ++token.current;
    const targets: [ActiveLocation, ActiveLocation] = [place, other];
    setRuns(IDLE);
    setPhase("running");
    for (const index of [0, 1] as const) {
      update(index, () => ({ status: "loading", steps: [] }));
      try {
        const response = await runResearchStream(researchRequestFor(targets[index], question.trim()), (step) => {
          if (token.current === mine) update(index, (run) => ({ ...run, steps: [...run.steps, step] }));
        });
        if (token.current !== mine) return;
        update(index, () => ({ status: "done", steps: [], response }));
      } catch (err) {
        if (token.current !== mine) return;
        const message = err instanceof ResearchApiError ? err.message : "Could not reach the research API. Is the backend running?";
        update(index, () => ({ status: "error", steps: [], error: message }));
      }
    }
    if (token.current === mine) setPhase("done");
  }

  function reset() {
    token.current++;
    setRuns(IDLE);
    setPhase("form");
  }

  const both = runs[0].response && runs[1].response ? ([runs[0].response, runs[1].response] as const) : null;

  return (
    <Dialog open={open} onClose={onClose} className="relative z-50">
      <DialogBackdrop transition className="fixed inset-0 bg-black/60 duration-150 data-[closed]:opacity-0" />
      <div className="fixed inset-0 overflow-y-auto">
      <div className="flex min-h-full items-center justify-center p-4 sm:p-8">
        <DialogPanel
          transition
          className="w-full max-w-6xl rounded-3xl border border-[var(--border)] bg-[var(--bg)] p-5 shadow-2xl duration-150 data-[closed]:scale-95 data-[closed]:opacity-0 sm:p-7"
        >
          <div className="mb-5 flex items-start justify-between gap-4">
            <div>
              <DialogTitle className="m-0 text-xl font-bold text-[var(--text-h)]">Compare two places</DialogTitle>
              <p className="m-0 mt-1 text-sm text-[var(--text-muted)]">
                The same question researched for each place, one after the other. It shows what each run found; it does not pick a winner.
              </p>
            </div>
            <button type="button" onClick={onClose} aria-label="Close" className="rounded-full p-1.5 text-[var(--text-muted)] hover:text-[var(--text-h)] focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none">
              <XMarkIcon className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>

          {phase === "form" && (
            <div className="flex flex-col gap-4">
              <p className="m-0 text-sm text-[var(--text)]">
                <span className="text-[var(--text-muted)]">First place: </span>
                <strong dir="auto">{nameA}</strong>
              </p>
              <div className="flex flex-col gap-2">
                <p className="m-0 text-sm text-[var(--text-muted)]">Second place</p>
                <div className="rounded-2xl bg-[#0b0a14] p-1">
                  <LocationSearchInput
                    value={query}
                    onChange={(value) => {
                      setQuery(value);
                      setOther(null);
                    }}
                    onSelect={(picked) => {
                      setOther(picked);
                      setQuery(picked.displayName);
                    }}
                    onSubmit={() => undefined}
                    placeholder="Search a place to compare with…"
                    autoFocus
                  />
                </div>
                {other ? (
                  <p className="m-0 text-xs text-[var(--supported)]">Picked: {other.displayName}</p>
                ) : (
                  <p className="m-0 text-xs text-[var(--text-muted)]">Choose one of the suggestions, so both places are exact.</p>
                )}
              </div>
              <div className="flex flex-col gap-2">
                <label className="text-sm text-[var(--text-muted)]" htmlFor="compare-question">
                  Question, asked of both
                </label>
                <textarea
                  id="compare-question"
                  value={question}
                  onChange={(event) => setTyped(event.target.value)}
                  rows={2}
                  placeholder="Would this be a good place for a college student?"
                  className="w-full resize-none rounded-xl border border-[var(--border)] bg-[var(--bg-alt)] p-3 text-sm text-[var(--text)] outline-none focus:border-[var(--accent)]"
                />
              </div>
              <p className="m-0 text-xs text-[var(--text-muted)]">Each run takes as long as a normal question, so expect roughly twice that.</p>
              <button type="button" onClick={start} disabled={!other || !question.trim()} className="w-fit rounded-full bg-[var(--accent)] px-6 py-2.5 text-sm font-semibold text-white transition hover:opacity-90 focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-40">
                Compare
              </button>
            </div>
          )}

          {phase !== "form" && (
            <div className="flex flex-col gap-5">
              <p className="m-0 text-sm text-[var(--text-muted)] italic" dir="auto">
                “{question.trim()}”
              </p>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <Column title={nameA} run={runs[0]} waitingFor={null} />
                <Column title={nameB} run={runs[1]} waitingFor={runs[0].status === "loading" ? nameA : null} />
              </div>

              {both && (
                <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-alt)] p-5" aria-label="What each run found">
                  <h3 className="m-0 mb-3 text-base font-bold text-[var(--text-h)]">What each run found</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[420px] border-collapse text-sm">
                      <thead>
                        <tr className="text-left text-[var(--text-muted)]">
                          <th className="py-2 pr-4 font-medium" />
                          <th className="py-2 pr-4 font-semibold text-[var(--text-h)]" dir="auto">{placeTitle(both[0])}</th>
                          <th className="py-2 font-semibold text-[var(--text-h)]" dir="auto">{placeTitle(both[1])}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {compareRows(both[0], both[1]).map((row) => (
                          <tr key={row.label} className="border-t border-[var(--border)]">
                            <th scope="row" className="py-2 pr-4 text-left font-normal text-[var(--text-muted)]">{row.label}</th>
                            <td className="py-2 pr-4 text-[var(--text-h)]">{row.a}</td>
                            <td className="py-2 text-[var(--text-h)]">{row.b}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="m-0 mt-3 text-xs text-[var(--text-muted)]">
                    These count what was found, not how good either place is: more sources does not make a better place, and a place
                    with fewer may simply be less written about.
                  </p>
                </section>
              )}

              <div className="flex flex-wrap items-center gap-3">
                {both && (
                  <button type="button" onClick={() => downloadText(comparisonFileName(both[0], both[1]), buildComparisonMarkdown(both[0], both[1]))} className={button}>
                    <ArrowDownTrayIcon className="h-4 w-4" aria-hidden="true" />
                    Download the comparison
                  </button>
                )}
                {both && (
                  <button type="button" onClick={() => printHtml(buildComparisonHtml(both[0], both[1]))} className={button}>
                    <PrinterIcon className="h-4 w-4" aria-hidden="true" />
                    Print / Save as PDF
                  </button>
                )}
                <button type="button" onClick={reset} disabled={phase === "running"} className={button}>
                  Compare other places
                </button>
              </div>
            </div>
          )}
        </DialogPanel>
      </div>
      </div>
    </Dialog>
  );
}
