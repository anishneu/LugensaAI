import { useState } from "react";
import { ArrowTopRightOnSquareIcon, ChatBubbleLeftRightIcon, ClockIcon } from "@heroicons/react/24/outline";
import type { Evidence } from "../types";
import { absoluteTimeFrom, evidenceText, relativeTimeFrom } from "../textUtils";
import { isForeign } from "./EvidenceList";
import { TranslationNote } from "./TranslationNote";
import { SOURCE_TYPE_ICON } from "../sourceTypeIcon";

interface CommunityVoicesProps {
  evidence: Evidence[];
}

const VOICE_SOURCE_TYPES = new Set(["community_forum", "review_aggregator"]);
const INITIAL_VISIBLE = 6;

type SortMode = "mixed" | "newest";

/** Which site a voice is from, as a person names it. Grouping by site is what makes the filter useful: Google Maps
 * alone can supply most of a business's voices, and the rest would be buried under it. */
function sourceLabel(item: Evidence): string {
  const host = (item.publisher ?? item.source_url).toLowerCase();
  if (host.includes("google")) return "Google Maps"; // the publisher reads "Google Maps"; its URL is maps.google.com
  if (host.includes("reddit.")) return "Reddit";
  if (host.includes("tripadvisor.")) return "TripAdvisor";
  return item.source_type === "review_aggregator" ? "Other review sites" : "Forums & communities";
}

const byEnglishThenNewest = (a: Evidence, b: Evidence) =>
  Number(isForeign(a)) - Number(isForeign(b)) || new Date(b.published_at ?? 0).getTime() - new Date(a.published_at ?? 0).getTime();

/** One from each site in turn, so the first screen shows the range of sources instead of the biggest one's whole list.
 * Sites take their turns in order of who has the newest voice; within a site, English first and newest first. */
function interleave(voices: Evidence[]): Evidence[] {
  const bySite = new Map<string, Evidence[]>();
  for (const voice of [...voices].sort(byEnglishThenNewest)) {
    const label = sourceLabel(voice);
    bySite.set(label, [...(bySite.get(label) ?? []), voice]);
  }
  const queues = [...bySite.values()].sort(
    (a, b) => new Date(b[0].published_at ?? 0).getTime() - new Date(a[0].published_at ?? 0).getTime(),
  );
  const mixed: Evidence[] = [];
  for (let round = 0; queues.some((q) => round < q.length); round++) {
    for (const queue of queues) if (round < queue.length) mixed.push(queue[round]);
  }
  return mixed;
}

export function isVoice(item: Evidence): boolean {
  return VOICE_SOURCE_TYPES.has(item.source_type);
}

function VoiceMedia({ item }: { item: Evidence }) {
  const [failed, setFailed] = useState(false);
  if (item.image_url && !failed) {
    return (
      <img className="h-16 w-16 flex-shrink-0 rounded-lg object-cover" src={item.image_url} alt={item.source_title} loading="lazy" onError={() => setFailed(true)} />
    );
  }
  return (
    <div className="flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-lg bg-[var(--bg)] text-xl" aria-hidden="true">
      {SOURCE_TYPE_ICON[item.source_type]}
    </div>
  );
}

/** A quotation, cut to six lines with a way to read the rest: one long review should not push everything else off screen. */
function Quote({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.length > 420;
  return (
    <div>
      <p className={`m-0 text-[13.5px] leading-relaxed text-[var(--text)] ${open || !long ? "" : "line-clamp-6"}`} dir="auto">
        “{text}”
      </p>
      {long && (
        <button type="button" onClick={() => setOpen((v) => !v)} className="mt-1 border-none bg-transparent p-0 text-xs font-semibold text-[var(--accent)] hover:underline">
          {open ? "Show less" : "Read more"}
        </button>
      )}
    </div>
  );
}

/** A real, dated post shows when it went up. Many forum posts carry no date at all; those say so instead of
 * borrowing the moment they were fetched. */
function When({ item }: { item: Evidence }) {
  if (!item.published_at) return <span className="text-[var(--text-muted)]">date unknown</span>;
  return (
    <span title={absoluteTimeFrom(item.published_at)} className="flex items-center gap-1">
      <ClockIcon className="h-3 w-3" aria-hidden="true" />
      {relativeTimeFrom(item.published_at)}
    </span>
  );
}

export function CommunityVoices({ evidence }: CommunityVoicesProps) {
  const [showAll, setShowAll] = useState(false);
  const [site, setSite] = useState<string>("All");
  const [sort, setSort] = useState<SortMode>("mixed");

  const all = evidence.filter(isVoice);
  const counts = new Map<string, number>();
  for (const voice of all) counts.set(sourceLabel(voice), (counts.get(sourceLabel(voice)) ?? 0) + 1);
  const sites = [...counts.entries()].sort((a, b) => b[1] - a[1]);

  const chosen = site === "All" ? all : all.filter((voice) => sourceLabel(voice) === site);
  const voices = sort === "mixed" && site === "All" ? interleave(chosen) : [...chosen].sort(byEnglishThenNewest);

  const visible = showAll ? voices : voices.slice(0, INITIAL_VISIBLE);
  const remaining = voices.length - visible.length;

  return (
    <section className="flex flex-col gap-3">
      <div>
        <h3 className="m-0 flex items-center gap-2 text-sm font-bold text-[var(--text-h)]">
          <ChatBubbleLeftRightIcon className="h-4.5 w-4.5 text-[var(--accent)]" aria-hidden="true" /> Community voices
        </h3>
        <p className="m-0 mt-1 text-xs leading-relaxed text-[var(--text-muted)]">
          Real comments and reviews from forums, Reddit, review sites and regional communities, including mixed or negative
          opinions. Shown for awareness, not fact-checked one by one: read the source before treating any single comment
          as settled fact.
        </p>
      </div>

      {all.length > 1 && (
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by source">
            {[["All", all.length] as [string, number], ...sites].map(([label, count]) => (
              <button
                key={label}
                type="button"
                onClick={() => {
                  setSite(label);
                  setShowAll(false);
                }}
                aria-pressed={site === label}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                  site === label
                    ? "border-[var(--accent)] bg-[var(--accent)] text-white"
                    : "border-[var(--border)] text-[var(--text)] hover:border-[var(--accent)]"
                }`}
              >
                {label} <span className={site === label ? "text-white/75" : "text-[var(--text-muted)]"}>{count}</span>
              </button>
            ))}
          </div>
          {site === "All" && (
            <div className="flex rounded-full border border-[var(--border)] bg-[var(--bg-alt)] p-0.5 text-xs">
              {([["mixed", "Mixed sources"], ["newest", "Newest first"]] as [SortMode, string][]).map(([mode, label]) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setSort(mode)}
                  className={`rounded-full px-3 py-1 font-medium transition-colors ${
                    sort === mode ? "bg-[var(--accent)] text-white" : "text-[var(--text-muted)] hover:text-[var(--text-h)]"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {voices.length === 0 ? (
        <p className="m-0 rounded-2xl border border-dashed border-[var(--border)] p-6 text-center text-sm text-[var(--text-muted)]">
          No forum or review commentary was found for this question.
        </p>
      ) : (
        <>
          <div className="flex flex-col gap-2.5">
            {visible.map((item) => (
                <article
                  key={item.evidence_id}
                  className="flex gap-3.5 rounded-xl border border-[var(--border)] bg-[var(--bg-alt)] p-4"
                >
                  <VoiceMedia item={item} />
                  <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                    <div className="flex flex-wrap items-center gap-2 text-[10.5px] text-[var(--text-muted)]">
                      <span className="rounded-full bg-[var(--accent-bg)] px-2 py-0.5 font-semibold tracking-wide text-[var(--accent)] uppercase">
                        {item.source_type.replace(/_/g, " ")}
                      </span>
                      <When item={item} />
                    </div>
                    <TranslationNote item={item} />
                    <Quote text={evidenceText(item)} />
                    <div className="mt-0.5 flex flex-wrap items-center justify-between gap-2 text-xs">
                      {item.publisher && <span className="text-[var(--text-muted)]">{item.publisher}</span>}
                      <a
                        href={item.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="ml-auto flex items-center gap-1 font-medium text-[var(--accent)] hover:underline"
                      >
                        View original
                        <ArrowTopRightOnSquareIcon className="h-3 w-3" aria-hidden="true" />
                      </a>
                    </div>
                  </div>
                </article>
              ))}
          </div>
          {remaining > 0 && (
            <button
              type="button"
              onClick={() => setShowAll(true)}
              className="self-center rounded-full border border-[var(--border)] px-4 py-1.5 text-xs font-medium text-[var(--text)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
            >
              Show {remaining} more
            </button>
          )}
        </>
      )}
    </section>
  );
}
