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
const INITIAL_VISIBLE = 4;

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

  // English first, then the rest; within each, newest (dated) before undated.
  const voices = evidence
    .filter(isVoice)
    .sort(
      (a, b) =>
        Number(isForeign(a)) - Number(isForeign(b)) ||
        new Date(b.published_at ?? 0).getTime() - new Date(a.published_at ?? 0).getTime(),
    );

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
                    <p className="m-0 text-[13.5px] leading-relaxed text-[var(--text)]" dir="auto">
                      “{evidenceText(item)}”
                    </p>
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
