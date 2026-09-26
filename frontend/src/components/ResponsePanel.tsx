import { useEffect, useState } from "react";
import { Tab, TabGroup, TabList, TabPanel, TabPanels } from "@headlessui/react";
import { ArrowDownTrayIcon, CheckCircleIcon, CheckIcon, ClipboardDocumentIcon, ExclamationTriangleIcon, PrinterIcon, SparklesIcon } from "@heroicons/react/24/outline";
import { fetchCapabilities } from "../api";
import type { Capabilities, QuerySession, ResearchResponse } from "../types";
import { downloadText, printHtml } from "../download";
import { buildReportHtml, buildReportMarkdown, reportFileName } from "../report";
import { cleanDisplayText } from "../textUtils";
import { ClaimsList } from "./ClaimsList";
import { CommunityVoices, isVoice } from "./CommunityVoices";
import type { EvidenceSortMode } from "./EvidenceList";
import { EvidenceList } from "./EvidenceList";
import { IconButton } from "./IconButton";
import { LiveSteps } from "./LiveSteps";
import { ResearchTrace } from "./ResearchTrace";
import { VerdictBanner } from "./VerdictBanner";

interface ResponsePanelProps {
  session: QuerySession | null;
}

function formatDuration(totalSeconds: number): string {
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
}

/** Elapsed time is the real measurement; the estimate beside it only sets expectations, because run time swings
 * from seconds to minutes depending on whether a local model is doing the reasoning. Once elapsed passes the
 * estimate, the estimate is dropped rather than left contradicting the clock. The steps beside it are the agent's own
 * trace, streamed as it records them (see `LiveSteps`); there is no invented "step 2 of 4", because how many steps a
 * run needs is not known until it ends. */
function ResearchProgress({ startedAt, capabilities }: { startedAt: string; capabilities: Capabilities | null }) {
  const [elapsed, setElapsed] = useState(() => Math.max(0, Math.round((Date.now() - new Date(startedAt).getTime()) / 1000)));

  useEffect(() => {
    const id = window.setInterval(() => {
      setElapsed(Math.max(0, Math.round((Date.now() - new Date(startedAt).getTime()) / 1000)));
    }, 1000);
    return () => window.clearInterval(id);
  }, [startedAt]);

  const overEstimate = capabilities != null && elapsed > capabilities.estimated_seconds_max;

  return (
    <div className="flex max-w-md flex-col items-center gap-1 text-center text-xs text-[var(--text-muted)]">
      <p className="m-0">
        <span className="font-semibold text-[var(--text)]">{formatDuration(elapsed)} elapsed</span>
        {capabilities && !overEstimate && (
          <>
            {" · "}usually {formatDuration(capabilities.estimated_seconds_min)}–{formatDuration(capabilities.estimated_seconds_max)}
          </>
        )}
        {overEstimate && " · taking longer than usual, still working"}
      </p>
      {capabilities?.first_run_warmup && (
        <p className="m-0">First question since the server started: it also loads the local search model once.</p>
      )}
    </div>
  );
}

/** The answer as a printed page, a Markdown file, or on the clipboard: icon buttons with a tooltip, at the right of the tab row.
 * Built in this page from the answer already shown; nothing is sent anywhere. */
function ExportButtons({ response }: { response: ResearchResponse }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(buildReportMarkdown(response));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be refused; the download still works.
    }
  }
  return (
    <>
      <IconButton label="Print / Save as PDF" onClick={() => printHtml(buildReportHtml(response))}>
        <PrinterIcon className="h-4 w-4" aria-hidden="true" />
      </IconButton>
      <IconButton label="Download report" onClick={() => downloadText(reportFileName(response), buildReportMarkdown(response))}>
        <ArrowDownTrayIcon className="h-4 w-4" aria-hidden="true" />
      </IconButton>
      <IconButton label={copied ? "Copied" : "Copy as Markdown"} onClick={copy}>
        {copied ? <CheckIcon className="h-4 w-4 text-[var(--supported)]" aria-hidden="true" /> : <ClipboardDocumentIcon className="h-4 w-4" aria-hidden="true" />}
      </IconButton>
    </>
  );
}

const cardClass = "rounded-2xl border border-[var(--border)] bg-[var(--bg-alt)] p-5";
const headingClass = "m-0 mb-2.5 text-[11px] font-bold tracking-[0.1em] text-[var(--text-muted)] uppercase";

const PRIORITY_CHIP: Record<string, string> = {
  high: "border-[var(--accent)] bg-[var(--accent-bg)] text-[var(--accent)]",
  medium: "border-[var(--border)] bg-[var(--bg)] text-[var(--text)]",
  low: "border-[var(--border)] bg-[var(--bg)] text-[var(--text-muted)]",
};

function Overview({ response }: { response: ResearchResponse }) {
  return (
    <div className="flex flex-col gap-4">
      <VerdictBanner response={response} />

      <section className={cardClass}>
        <h3 className={headingClass}>Summary</h3>
        <p className="m-0 text-[15px] leading-relaxed text-[var(--text)]" dir="auto">
          {cleanDisplayText(response.summary)}
        </p>
      </section>

      {response.key_findings.length > 0 && (
        <section className={cardClass}>
          <h3 className={headingClass}>Key findings</h3>
          <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
            {response.key_findings.map((finding, i) => (
              <li
                key={i}
                className="flex items-start gap-2.5 text-sm leading-relaxed text-[var(--text)]"
                dir="auto"
              >
                <CheckCircleIcon className="mt-0.5 h-4.5 w-4.5 flex-shrink-0 text-[var(--supported)]" aria-hidden="true" />
                {cleanDisplayText(finding)}
              </li>
            ))}
          </ul>
        </section>
      )}

      {response.details && (
        <section className={cardClass}>
          <h3 className={headingClass}>Details</h3>
          <div className="flex flex-col gap-3 text-sm leading-relaxed text-[var(--text)]" dir="auto">
            {cleanDisplayText(response.details)
              .split("\n\n")
              .filter(Boolean)
              .map((paragraph, i) => (
                <p key={i} className="m-0">
                  {paragraph}
                </p>
              ))}
          </div>
        </section>
      )}

      <section className={cardClass}>
        <h3 className={headingClass}>Research plan</h3>
        <div className="flex flex-wrap gap-2">
          {response.topics.map((topic) => (
            <span
              key={topic.topic_id}
              title={topic.reason}
              className={`rounded-full border px-3 py-1 text-xs font-medium capitalize ${PRIORITY_CHIP[topic.priority] ?? PRIORITY_CHIP.medium}`}
            >
              {topic.topic_id.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}

function Details({ response }: { response: ResearchResponse }) {
  return (
    <div className="flex flex-col gap-4">
      {response.limitations.length > 0 && (
        <section className="rounded-2xl border border-amber-500/40 bg-amber-500/[0.07] p-5">
          <h3 className="m-0 mb-2.5 flex items-center gap-2 text-sm font-bold text-[var(--insufficient)]">
            <ExclamationTriangleIcon className="h-4.5 w-4.5" aria-hidden="true" /> Known limitations
          </h3>
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {response.limitations.map((limitation, i) => (
              <li key={i} className="text-[13px] leading-relaxed text-[var(--text)]">
                {limitation}
              </li>
            ))}
          </ul>
        </section>
      )}
      <ResearchTrace trace={response.research_trace} />
    </div>
  );
}

const shell = "mx-5 my-4";

export function ResponsePanel({ session }: ResponsePanelProps) {
  const [sortMode, setSortMode] = useState<EvidenceSortMode>("relevance");
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);

  // Config-derived, so it's fetched once rather than per question.
  useEffect(() => {
    fetchCapabilities().then(setCapabilities);
  }, []);

  if (!session) {
    return (
      <div className={`${shell} flex flex-col items-center gap-3 rounded-2xl border border-dashed border-[var(--border)] px-6 py-16 text-center`}>
        <SparklesIcon className="h-8 w-8 text-[var(--accent)]" aria-hidden="true" />
        <p className="m-0 max-w-sm text-sm text-[var(--text-muted)]">Ask a question to see the agent's research here.</p>
      </div>
    );
  }

  if (session.status === "loading") {
    return (
      <div className={`${shell} flex flex-col items-center gap-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-alt)] px-6 py-10 text-center`}>
        <div className="h-9 w-9 animate-spin rounded-full border-[3px] border-[var(--border)] border-t-[var(--accent)]" />
        <div className="flex max-w-xl flex-col gap-1.5">
          <p className="m-0 line-clamp-2 text-[15px] font-medium text-[var(--text-h)]" dir="auto" title={session.question}>
            Researching “{session.question}”…
          </p>
          <ResearchProgress startedAt={session.askedAt} capabilities={capabilities} />
        </div>
        <LiveSteps steps={session.steps ?? []} />
      </div>
    );
  }

  if (session.status === "error" || !session.response) {
    return (
      <div className={shell}>
        <div className="flex items-start gap-3 rounded-2xl border border-red-500/40 bg-red-500/[0.08] p-5 text-sm text-[var(--contradicted)]">
          <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
          {session.error ?? "Something went wrong."}
        </div>
      </div>
    );
  }

  const response = session.response;
  const voiceCount = response.evidence.filter(isVoice).length;
  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "community", label: "Community", count: voiceCount },
    { id: "claims", label: "Claims", count: response.claims.length },
    { id: "evidence", label: "Evidence", count: response.evidence.length },
    { id: "details", label: "Details" },
  ];

  return (
    <div className={shell}>
      <p className="m-0 mb-4 text-[15px] text-[var(--text-muted)] italic" dir="auto">
        “{response.question}”
      </p>

      {/* Keyed by question, so each answer opens on Overview rather than on whatever tab the last one left. */}
      <TabGroup key={session.id}>
        <div className="mb-5 flex items-end justify-between gap-3 shadow-[inset_0_-1px_0_var(--border)]">
        <TabList className="flex min-w-0 gap-x-4 overflow-x-auto xl:gap-x-5">
          {tabs.map((tab) => (
            <Tab
              key={tab.id}
              className="flex flex-shrink-0 items-center gap-2 border-b-2 border-transparent px-1 pt-1 pb-3 text-sm font-medium whitespace-nowrap text-[var(--text-muted)] outline-none transition-colors data-[focus]:rounded-sm data-[focus]:ring-2 data-[focus]:ring-violet-500 data-[hover]:border-[var(--text-muted)] data-[hover]:text-[var(--text-h)] data-[selected]:border-[var(--accent)] data-[selected]:text-[var(--accent)]"
            >
              {({ selected }) => (
                <>
                  {tab.label}
                  {tab.count != null && (
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${selected ? "bg-[var(--accent-bg)] text-[var(--accent)]" : "bg-[var(--bg-alt)] text-[var(--text-muted)]"}`}
                    >
                      {tab.count}
                    </span>
                  )}
                </>
              )}
            </Tab>
          ))}
        </TabList>
        <div className="mb-2 flex flex-shrink-0 gap-1.5">
          <ExportButtons response={response} />
        </div>
        </div>

        <TabPanels>
          {[
            <Overview key="overview" response={response} />,
            <CommunityVoices key="community" evidence={response.evidence} />,
            <ClaimsList key="claims" claims={response.claims} />,
            <section key="evidence" className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="m-0 text-xs text-[var(--text-muted)]">
                  English sources are listed first; translated ones are labeled and open to the original.
                </p>
                <div className="flex rounded-full border border-[var(--border)] bg-[var(--bg-alt)] p-0.5 text-xs">
                  {(["relevance", "newest"] as const).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setSortMode(mode)}
                      className={`rounded-full px-3 py-1 font-medium transition-colors ${
                        sortMode === mode ? "bg-[var(--accent)] text-white" : "text-[var(--text-muted)] hover:text-[var(--text-h)]"
                      }`}
                    >
                      {mode === "relevance" ? "Most relevant" : "Newest first"}
                    </button>
                  ))}
                </div>
              </div>
              <EvidenceList evidence={response.evidence} sortMode={sortMode} />
            </section>,
            <Details key="details" response={response} />,
          ].map((content, i) => (
            <TabPanel key={tabs[i].id} className="outline-none">
              {content}
            </TabPanel>
          ))}
        </TabPanels>
      </TabGroup>
    </div>
  );
}
