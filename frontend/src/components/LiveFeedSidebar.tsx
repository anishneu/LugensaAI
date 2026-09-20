import { useCallback, useEffect, useRef, useState } from "react";
import { Tab, TabGroup, TabList, TabPanel, TabPanels } from "@headlessui/react";
import { ArrowPathIcon, ClockIcon, NewspaperIcon, UserGroupIcon } from "@heroicons/react/24/outline";
import { fetchCapabilities, fetchLiveFeed, ResearchApiError } from "../api";
import { absoluteTimeFrom, evidenceText, relativeTimeFrom } from "../textUtils";
import { TranslationNote } from "./TranslationNote";
import { SOURCE_TYPE_ICON } from "../sourceTypeIcon";
import type { ActiveLocation, Evidence } from "../types";

interface LiveFeedSidebarProps {
  location: ActiveLocation;
}

// A cold load is two to four real, billed Tavily searches (the backend caches them for an hour). Auto-refresh
// matches that hour, so it costs nothing while the cache is warm; only the manual button forces a fresh search.
const AUTO_REFRESH_MS = 60 * 60 * 1000;
const PAGE_SIZE = 6;

function regionLabel(location: ActiveLocation): string {
  return [location.city, location.region].filter(Boolean).join(", ") || location.displayName;
}

const SCOPE_CHIP: Record<string, string> = { region: "Wider region" };

function FeedMedia({ item }: { item: Evidence }) {
  const [failed, setFailed] = useState(false);
  if (item.image_url && !failed) {
    return (
      <img className="h-14 w-14 flex-shrink-0 rounded-lg object-cover" src={item.image_url} alt="" loading="lazy" onError={() => setFailed(true)} />
    );
  }
  return (
    <div className="flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-lg bg-[var(--bg)] text-xl" aria-hidden="true">
      {SOURCE_TYPE_ICON[item.source_type]}
    </div>
  );
}

function FeedCard({ item }: { item: Evidence }) {
  const scope = item.metadata.feed_scope;
  const description = evidenceText(item);
  return (
    <article
      className="flex gap-3 rounded-xl border border-[var(--border)] bg-[var(--bg)] p-3"
    >
      <FeedMedia item={item} />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10.5px] text-[var(--text-muted)]">
          {item.published_at ? (
            <span className="flex items-center gap-1" title={absoluteTimeFrom(item.published_at)}>
              <ClockIcon className="h-3 w-3" aria-hidden="true" />
              {relativeTimeFrom(item.published_at)}
            </span>
          ) : (
            <span>date unknown</span>
          )}
          {scope && SCOPE_CHIP[scope] && (
            <span
              className="rounded-full bg-[var(--accent-bg)] px-2 py-px font-medium text-[var(--accent)]"
              title={`Not much was found for the exact area, so this is about ${item.location_scope}`}
            >
              {SCOPE_CHIP[scope]} · {item.location_scope}
            </span>
          )}
        </div>
        <a
          href={item.source_url}
          target="_blank"
          rel="noreferrer"
          className="line-clamp-2 text-[13px] leading-snug font-semibold text-[var(--text-h)] no-underline hover:text-[var(--accent)]"
          dir="auto"
        >
          {item.source_title}
        </a>
        {item.publisher && (
          <a
            href={item.source_url}
            target="_blank"
            rel="noreferrer"
            className="truncate text-[11px] text-[var(--accent)] no-underline hover:underline"
            title={item.source_url}
          >
            {item.publisher}
          </a>
        )}
        {description && (
          <p className="m-0 line-clamp-3 text-xs leading-relaxed text-[var(--text-muted)]" dir="auto">
            {description}
          </p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <TranslationNote item={item} inline />
        </div>
      </div>
    </article>
  );
}

function FeedList({ items, empty }: { items: Evidence[]; empty: string }) {
  const [visible, setVisible] = useState(PAGE_SIZE);
  if (items.length === 0) {
    return <p className="m-0 rounded-xl border border-dashed border-[var(--border)] p-4 text-center text-xs leading-relaxed text-[var(--text-muted)]">{empty}</p>;
  }
  return (
    <div className="flex flex-col gap-2.5">
      {items.slice(0, visible).map((item) => (
        <FeedCard key={item.evidence_id} item={item} />
      ))}
      {items.length > visible && (
        <button
          type="button"
          onClick={() => setVisible((v) => v + PAGE_SIZE)}
          className="self-center rounded-full border border-[var(--border)] px-4 py-1.5 text-xs font-medium text-[var(--text)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
        >
          Show {Math.min(PAGE_SIZE, items.length - visible)} more
        </button>
      )}
    </div>
  );
}

export function LiveFeedSidebar({ location }: LiveFeedSidebarProps) {
  const [feed, setFeed] = useState<Evidence[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  // Whether the backend has live search at all. An empty feed means two different things: no key, or nothing
  // published about this place lately (normal for a village).
  const [liveSearch, setLiveSearch] = useState<boolean | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback((refresh = false) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    fetchLiveFeed(
      {
        location: location.rawQuery,
        latitude: location.latitude,
        longitude: location.longitude,
        city: location.city,
        region: location.region,
        country: location.country,
      },
      controller.signal,
      refresh,
    )
      .then((items) => {
        setFeed(items);
        setLastUpdated(new Date().toISOString());
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(err instanceof ResearchApiError ? err.message : "Could not load the live feed.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, [location.rawQuery, location.latitude, location.longitude, location.city, location.region, location.country]);

  useEffect(() => {
    fetchCapabilities().then((caps) => setLiveSearch(caps ? caps.live_search : null));
  }, []);

  useEffect(() => {
    load();
    const interval = window.setInterval(() => load(), AUTO_REFRESH_MS);
    return () => {
      window.clearInterval(interval);
      abortRef.current?.abort();
    };
  }, [load]);

  const news = feed.filter((item) => item.metadata.feed_kind !== "community");
  const community = feed.filter((item) => item.metadata.feed_kind === "community");
  const label = regionLabel(location);
  const noKey = liveSearch === false;
  const tabs = [
    { id: "news", label: "News", Icon: NewspaperIcon, items: news, empty: `No news about ${label} or the region around it in the last 30 days.` },
    { id: "community", label: "Community", Icon: UserGroupIcon, items: community, empty: `No forum or Reddit conversation about ${label} was found.` },
  ];

  return (
    <div className="flex flex-col gap-4 p-5">
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <h2 className="m-0 text-[15px] font-bold text-[var(--text-h)]">Live feed</h2>
          <button
            type="button"
            onClick={() => load(true)}
            disabled={loading}
            title="Refresh now"
            aria-label="Refresh the live feed"
            className="rounded-full border border-[var(--border)] p-1.5 text-[var(--text)] transition hover:border-[var(--accent)] disabled:cursor-wait disabled:opacity-60"
          >
            <ArrowPathIcon className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
          </button>
        </div>
        <p className="m-0 text-xs leading-relaxed text-[var(--text-muted)]">
          What's being said about {label}: news from the last 30 days and community conversation. When the area itself has
          little, it widens once to the region around it, and says so. It never goes country-wide.
        </p>
        {lastUpdated && <p className="m-0 text-[10.5px] text-[var(--text-muted)]">{loading ? "Refreshing…" : `Updated ${relativeTimeFrom(lastUpdated)}`}</p>}
      </div>

      {error && <p className="m-0 rounded-xl border border-red-500/40 bg-red-500/[0.07] p-3 text-xs text-[var(--contradicted)]">{error}</p>}

      {!error && noKey && (
        <p className="m-0 rounded-xl border border-dashed border-[var(--border)] p-4 text-center text-xs leading-relaxed text-[var(--text-muted)]">
          No live feed available: this needs a Tavily API key configured on the backend (<code>TAVILY_API_KEY</code>).
        </p>
      )}

      {!error && !noKey && (
        <TabGroup>
          <TabList className="mb-3 flex gap-1 rounded-full border border-[var(--border)] bg-[var(--bg-alt)] p-1">
            {tabs.map(({ id, label: tabLabel, Icon, items }) => (
              <Tab
                key={id}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-[var(--text-muted)] outline-none transition-colors data-[hover]:text-[var(--text-h)] data-[selected]:bg-[var(--accent)] data-[selected]:text-white data-[focus]:ring-2 data-[focus]:ring-violet-500"
              >
                {({ selected }) => (
                  <>
                    <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                    {tabLabel}
                    <span className={`rounded-full px-1.5 text-[10px] ${selected ? "bg-white/25" : "bg-[var(--bg)]"}`}>{items.length}</span>
                  </>
                )}
              </Tab>
            ))}
          </TabList>
          <TabPanels>
            {tabs.map(({ id, items, empty }) => (
              <TabPanel key={id} className="outline-none">
                {loading && feed.length === 0 ? (
                  <div className="flex flex-col gap-2.5" aria-busy="true">
                    {[0, 1, 2].map((n) => (
                      <div key={n} className="h-24 animate-pulse rounded-xl bg-[var(--bg-alt)]" />
                    ))}
                  </div>
                ) : (
                  <FeedList items={items} empty={empty} />
                )}
              </TabPanel>
            ))}
          </TabPanels>
        </TabGroup>
      )}
    </div>
  );
}
