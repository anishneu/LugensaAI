import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowPathIcon, ArrowTopRightOnSquareIcon, ClockIcon, MapPinIcon } from "@heroicons/react/24/outline";
import { fetchCapabilities, fetchLiveFeed, ResearchApiError } from "../api";
import { absoluteTimeFrom, evidenceText, relativeTimeFrom } from "../textUtils";
import { TranslationNote } from "./TranslationNote";
import { googleNewsSearchUrl } from "../maps";
import { SOURCE_TYPE_ICON } from "../sourceTypeIcon";
import type { ActiveLocation, Evidence } from "../types";

interface LiveFeedSidebarProps {
  location: ActiveLocation;
}

// The backend caches a place's feed for 30 minutes; refreshing on the same beat costs nothing while it is warm, and
// only the manual button forces a fresh load.
const AUTO_REFRESH_MS = 30 * 60 * 1000;
const PAGE_SIZE = 8;
const NOW_MINUTES = 60;

// One colour per kind of item, tinted so it reads in light and dark and never carries meaning on its own (the label does).
const CATEGORY_STYLE: Record<string, string> = {
  "Crime & safety": "bg-red-500/10 text-red-700 dark:text-red-300",
  "Accidents & traffic": "bg-amber-500/10 text-amber-700 dark:text-amber-300",
  "Weather & alerts": "bg-sky-500/10 text-sky-700 dark:text-sky-300",
  Business: "bg-violet-500/10 text-violet-700 dark:text-violet-300",
  "Events & tourism": "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  "Development & transport": "bg-slate-500/10 text-slate-700 dark:text-slate-300",
  Community: "bg-pink-500/10 text-pink-700 dark:text-pink-300",
  News: "bg-[var(--bg-alt)] text-[var(--text-muted)]",
};

/** Which heading an item sits under: "Now" for the last hour, then "Today", "Yesterday", and a date after that. */
function groupLabel(iso: string, nowMs: number): string {
  const when = new Date(iso);
  if ((nowMs - when.getTime()) / 60000 < NOW_MINUTES) return "Now";
  const startOfToday = new Date(nowMs);
  startOfToday.setHours(0, 0, 0, 0);
  const day = 24 * 60 * 60 * 1000;
  if (when.getTime() >= startOfToday.getTime()) return "Today";
  if (when.getTime() >= startOfToday.getTime() - day) return "Yesterday";
  return when.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

/** A small red dot that blinks: the feed is live. Steady, not blinking, for anyone who has asked for reduced motion. */
function LiveDot() {
  return (
    <span className="relative flex h-1.5 w-1.5 flex-shrink-0" role="img" aria-label="Live">
      <span className="absolute inline-flex h-full w-full rounded-full bg-red-500 opacity-70 motion-safe:animate-ping" />
      <span className="live-blink relative inline-flex h-1.5 w-1.5 rounded-full bg-red-500" />
    </span>
  );
}

function FeedMedia({ item }: { item: Evidence }) {
  const [failed, setFailed] = useState(false);
  if (item.image_url && !failed) {
    return (
      <img className="h-12 w-12 flex-shrink-0 rounded-lg object-cover" src={item.image_url} alt="" loading="lazy" onError={() => setFailed(true)} />
    );
  }
  return (
    <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-lg bg-[var(--bg)] text-lg" aria-hidden="true">
      {item.metadata.feed_kind === "community" ? "💬" : SOURCE_TYPE_ICON[item.source_type]}
    </div>
  );
}

function FeedCard({ item }: { item: Evidence }) {
  const description = evidenceText(item);
  const category = item.metadata.feed_category;
  const place = item.metadata.feed_place;
  const near = item.metadata.feed_scope === "near";
  return (
    <article className="flex gap-3 rounded-xl border border-[var(--border)] bg-[var(--bg)] p-3">
      <FeedMedia item={item} />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[10.5px]">
          {category && <span className={`rounded-full px-2 py-px font-semibold ${CATEGORY_STYLE[category] ?? CATEGORY_STYLE.News}`}>{category}</span>}
          {place && (
            <span
              className="flex min-w-0 items-center gap-0.5 rounded-full border border-[var(--border)] px-1.5 py-px text-[var(--text)]"
              title={near ? `About ${place}, at or near the place you picked` : `Nothing was found at or near the place you picked, so this is about ${place}`}
            >
              <MapPinIcon className="h-3 w-3 flex-shrink-0" aria-hidden="true" />
              <span className="truncate">{near ? `Near ${place}` : place}</span>
            </span>
          )}
        </div>
        <a
          href={item.source_url}
          target="_blank"
          rel="noreferrer"
          className="line-clamp-3 text-[13px] leading-snug font-semibold text-[var(--text-h)] no-underline hover:text-[var(--accent)]"
          dir="auto"
        >
          {item.source_title}
        </a>
        <div className="flex flex-wrap items-center gap-x-2 text-[10.5px] text-[var(--text-muted)]">
          {item.published_at && (
            <span className="flex items-center gap-1" title={absoluteTimeFrom(item.published_at)}>
              <ClockIcon className="h-3 w-3" aria-hidden="true" />
              {relativeTimeFrom(item.published_at)}
            </span>
          )}
          {(item.publisher || item.metadata.subreddit) && (
            <span className="truncate text-[var(--accent)]" title={item.source_url}>
              {item.publisher ?? `r/${item.metadata.subreddit}`}
            </span>
          )}
        </div>
        {description && (
          <p className="m-0 line-clamp-3 text-xs leading-relaxed text-[var(--text-muted)]" dir="auto">
            {description}
          </p>
        )}
        <TranslationNote item={item} inline />
      </div>
    </article>
  );
}

function Timeline({ items, nowMs }: { items: Evidence[]; nowMs: number }) {
  const [visible, setVisible] = useState(PAGE_SIZE);
  const shown = items.slice(0, visible);
  return (
    <div className="flex flex-col gap-2.5">
      {shown.map((item, i) => {
        const label = item.published_at ? groupLabel(item.published_at, nowMs) : "";
        const heading = label && (i === 0 || label !== (shown[i - 1].published_at ? groupLabel(shown[i - 1].published_at as string, nowMs) : ""));
        return (
          <div key={item.evidence_id} className="flex flex-col gap-2.5">
            {heading && (
              <h3 className={`m-0 mt-1 flex items-center gap-1.5 text-[10.5px] font-bold tracking-[0.14em] uppercase ${label === "Now" ? "text-red-600 dark:text-red-400" : "text-[var(--text-muted)]"}`}>
                {label}
                <span className="h-px flex-1 bg-[var(--border)]" aria-hidden="true" />
              </h3>
            )}
            <FeedCard item={item} />
          </div>
        );
      })}
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
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  // The clock the "Now" / "Today" headings are worked out against, moved on whenever the feed is (re)loaded.
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [category, setCategory] = useState<string | null>(null);
  // Whether the backend has any source for the feed at all. An empty feed means two different things: no source, or
  // nothing published about this place in the last 30 days.
  const [available, setAvailable] = useState<boolean | null>(null);
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
        setLoaded(true);
        setNowMs(Date.now());
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
    fetchCapabilities().then((caps) => setAvailable(caps ? (caps.live_feed ?? caps.live_search) : null));
  }, []);

  useEffect(() => {
    setLoaded(false);
    setCategory(null);
    load();
    const interval = window.setInterval(() => load(), AUTO_REFRESH_MS);
    return () => {
      window.clearInterval(interval);
      abortRef.current?.abort();
    };
  }, [load]);

  // The kinds present, in the order they first appear (newest first), each with its count: the filter offers only these.
  const categories = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of feed) {
      const name = item.metadata.feed_category || "News";
      counts.set(name, (counts.get(name) ?? 0) + 1);
    }
    return [...counts.entries()];
  }, [feed]);
  const active = category && categories.some(([name]) => name === category) ? category : null;
  const shown = active ? feed.filter((item) => (item.metadata.feed_category || "News") === active) : feed;

  return (
    <div className="flex flex-col gap-4 p-5">
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <h2 className="m-0 flex items-center gap-2 text-[15px] font-bold text-[var(--text-h)]">
            Live feed
            <LiveDot />
          </h2>
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
          New in the last 30 days: news, safety, accidents, business, events and community posts. Anything at or near the place comes
          first, and the city only when there is nothing there.
        </p>
        {lastUpdated && <p className="m-0 text-[10.5px] text-[var(--text-muted)]">{loading ? "Refreshing…" : `Updated ${relativeTimeFrom(lastUpdated)}`}</p>}
      </div>

      {error && <p className="m-0 rounded-xl border border-red-500/40 bg-red-500/[0.07] p-3 text-xs text-[var(--contradicted)]">{error}</p>}

      {!error && available === false && (
        <p className="m-0 rounded-xl border border-dashed border-[var(--border)] p-4 text-center text-xs leading-relaxed text-[var(--text-muted)]">
          The live feed has no source on this server: it needs live lookups switched on, or a Tavily key (<code>TAVILY_API_KEY</code>).
        </p>
      )}

      {!error && available !== false && (
        <>
          {categories.length > 1 && (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter the feed by kind">
              {[["All", feed.length] as [string, number], ...categories].map(([name, count]) => {
                const on = (name === "All" && !active) || name === active;
                return (
                  <button
                    key={name}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setCategory(name === "All" ? null : name)}
                    className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition ${
                      on ? "border-[var(--accent)] bg-[var(--accent)] text-white" : "border-[var(--border)] text-[var(--text)] hover:border-[var(--accent)]"
                    }`}
                  >
                    {name} <span className={on ? "text-white/80" : "text-[var(--text-muted)]"}>{count}</span>
                  </button>
                );
              })}
            </div>
          )}

          {!loaded && loading ? (
            <div className="flex flex-col gap-2.5" aria-busy="true">
              {[0, 1, 2].map((n) => (
                <div key={n} className="h-24 animate-pulse rounded-xl bg-[var(--bg-alt)]" />
              ))}
            </div>
          ) : shown.length === 0 ? (
            // Nothing new in the window: nothing is shown, and no older item stands in for it.
            <p className="m-0 py-6 text-center text-xs text-[var(--text-muted)]">Nothing new in the last 30 days.</p>
          ) : (
            <Timeline key={`${active ?? "all"}-${feed.length}`} items={shown} nowMs={nowMs} />
          )}
          <a
            href={googleNewsSearchUrl(location)}
            target="_blank"
            rel="noreferrer"
            className="flex w-fit items-center gap-1.5 self-end text-xs font-medium text-[var(--accent)] hover:underline"
            title="The feed's news comes from Google News' public feed, which lists headlines. This opens Google News' own results for the place."
          >
            See more on Google News
            <ArrowTopRightOnSquareIcon className="h-3.5 w-3.5" aria-hidden="true" />
          </a>
        </>
      )}
    </div>
  );
}
