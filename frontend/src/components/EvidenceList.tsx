import { useState } from "react";
import { Disclosure, DisclosureButton, DisclosurePanel } from "@headlessui/react";
import { ChevronRightIcon } from "@heroicons/react/24/outline";
import type { Evidence } from "../types";
import { evidenceText } from "../textUtils";
import { TranslationNote } from "./TranslationNote";
import { SOURCE_TYPE_ICON } from "../sourceTypeIcon";

export type EvidenceSortMode = "relevance" | "newest";

interface EvidenceListProps {
  evidence: Evidence[];
  sortMode: EvidenceSortMode;
}

/** A source written in another language (machine-translated or not) is secondary to one in the reader's own. */
export function isForeign(item: Evidence): boolean {
  const language = item.metadata.language;
  return Boolean(language && language !== "en");
}

function sortedWithin(items: Evidence[], sortMode: EvidenceSortMode): Evidence[] {
  const copy = [...items];
  if (sortMode === "newest") {
    copy.sort((a, b) => {
      const at = new Date(a.published_at ?? a.retrieved_at).getTime();
      const bt = new Date(b.published_at ?? b.retrieved_at).getTime();
      return bt - at;
    });
  } else {
    copy.sort((a, b) => Number(isForeign(a)) - Number(isForeign(b)) || (b.relevance_score ?? 0) - (a.relevance_score ?? 0));
  }
  return copy;
}

function EvidenceMedia({ item }: { item: Evidence }) {
  const [failed, setFailed] = useState(false);
  if (item.image_url && !failed) {
    return (
      <img
        className="h-20 w-20 flex-shrink-0 rounded-lg object-cover"
        src={item.image_url}
        alt={item.source_title}
        loading="lazy"
        onError={() => setFailed(true)}
      />
    );
  }
  return (
    <div className="flex h-20 w-20 flex-shrink-0 items-center justify-center rounded-lg bg-[var(--bg)] text-2xl" aria-hidden="true">
      {SOURCE_TYPE_ICON[item.source_type]}
    </div>
  );
}

function EvidenceCard({ item }: { item: Evidence }) {
  return (
    <article className="flex gap-3.5 rounded-xl border border-[var(--border)] bg-[var(--bg)] p-3.5">
      <EvidenceMedia item={item} />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2 text-[10.5px] text-[var(--text-muted)]">
          <span className="rounded-full bg-[var(--accent-bg)] px-2 py-0.5 font-semibold tracking-wide text-[var(--accent)] uppercase">
            {item.source_type.replace(/_/g, " ")}
          </span>
          {item.relevance_score != null && <span title="Relevance score assigned by the retriever">● {item.relevance_score.toFixed(2)}</span>}
          {item.recency_days != null && <span>{item.recency_days}d old</span>}
        </div>
        <a
          href={item.source_url}
          target="_blank"
          rel="noreferrer"
          className="text-sm leading-snug font-semibold text-[var(--text-h)] no-underline hover:text-[var(--accent)]"
          dir="auto"
        >
          {item.source_title}
        </a>
        {item.publisher && <span className="text-xs text-[var(--text-muted)]">{item.publisher}</span>}
        <TranslationNote item={item} />
        <p className="m-0 line-clamp-4 text-[13px] leading-relaxed text-[var(--text)]" dir="auto">
          {evidenceText(item)}
        </p>
        <a href={item.source_url} target="_blank" rel="noreferrer" className="w-fit text-xs font-medium text-[var(--accent)] hover:underline">
          Read full source →
        </a>
      </div>
    </article>
  );
}

export function EvidenceList({ evidence, sortMode }: EvidenceListProps) {
  if (evidence.length === 0) {
    return (
      <p className="m-0 rounded-2xl border border-dashed border-[var(--border)] p-6 text-center text-sm text-[var(--text-muted)]">
        No evidence was collected.
      </p>
    );
  }

  const byTopic = new Map<string, Evidence[]>();
  for (const item of evidence) {
    const list = byTopic.get(item.topic) ?? [];
    list.push(item);
    byTopic.set(item.topic, list);
  }

  return (
    <div className="flex flex-col gap-2.5">
      {[...byTopic.entries()].map(([topic, items]) => (
        <Disclosure key={topic} as="div" className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--bg-alt)]">
          <DisclosureButton className="group flex w-full items-center gap-2.5 px-4 py-3 text-left outline-none data-[focus]:ring-2 data-[focus]:ring-violet-500">
            <ChevronRightIcon className="h-4 w-4 text-[var(--text-muted)] transition-transform group-data-[open]:rotate-90" aria-hidden="true" />
            <h4 className="m-0 flex-1 text-sm font-semibold text-[var(--text-h)] capitalize">{topic.replace(/_/g, " ")}</h4>
            <span className="rounded-full bg-[var(--bg)] px-2 py-0.5 text-[11px] text-[var(--text-muted)]">{items.length}</span>
          </DisclosureButton>
          <DisclosurePanel transition className="flex origin-top flex-col gap-2.5 px-3 pb-3 duration-200 ease-out data-[closed]:-translate-y-1 data-[closed]:opacity-0">
            {sortedWithin(items, sortMode).map((item) => (
              <EvidenceCard key={item.evidence_id} item={item} />
            ))}
          </DisclosurePanel>
        </Disclosure>
      ))}
    </div>
  );
}
