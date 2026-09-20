import { useEffect, useState } from "react";
import { Popover, PopoverButton, PopoverPanel } from "@headlessui/react";
import { ArrowTopRightOnSquareIcon, ChevronDownIcon, ClockIcon, StarIcon } from "@heroicons/react/24/solid";
import { fetchPlaceProfile, fetchPopularPlaces, ResearchApiError } from "../../api";
import { absoluteTimeFrom, relativeTimeFrom } from "../../textUtils";
import type { ActiveLocation, PlaceProfile, PopularPlace } from "../../types";

export type GoogleState =
  | { key: string; status: "profile"; profile: PlaceProfile; others: PopularPlace[] }
  | { key: string; status: "popular"; places: PopularPlace[] }
  | { key: string; status: "not-configured" }
  | { key: string; status: "no-match" }
  | { key: string; status: "failed" };

const languageNames = new Intl.DisplayNames(["en"], { type: "language" });

const wordsOf = (text: string) => new Set(text.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((w) => w.length > 1));

/** The same place's name: the same words, in any order ("Ginkaku-ji" and "Ginkaku ji"); one extra word is another place. */
function sameName(a: string, b: string): boolean {
  const wa = wordsOf(a);
  const wb = wordsOf(b);
  return wa.size > 0 && wa.size === wb.size && [...wa].every((w) => wb.has(w));
}

function Stars({ value }: { value: number }) {
  const full = Math.round(value);
  return (
    <span className="inline-flex items-center gap-px align-middle" aria-label={`${value} out of 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <StarIcon key={n} className={`h-3.5 w-3.5 ${n <= full ? "text-amber-500" : "text-[var(--border)]"}`} aria-hidden="true" />
      ))}
    </span>
  );
}

const NOTE = "m-0 rounded-xl border border-dashed border-[var(--border)] px-4 py-3 text-xs leading-relaxed text-[var(--text-muted)]";

/** What Google Maps says about the pin. `null` while it is being asked. A business gets its listing; a landmark such as a
 * temple, which Google lists as an attraction, gets its listing too when a well-known place right there has the pin's own
 * name; anything else (an area, a street corner) gets the well-known places around it. The panel reads this to label its
 * header, so it can say when the content changes from one to the other. */
export function useGoogleData(location: ActiveLocation): GoogleState | null {
  const { latitude, longitude, isBusiness } = location;
  const name = location.displayName.split(",")[0].trim();
  const key = latitude != null && longitude != null ? `${isBusiness ? "profile" : "popular"}|${name}|${latitude},${longitude}` : "";
  const [state, setState] = useState<GoogleState | null>(null);

  useEffect(() => {
    if (!key || latitude == null || longitude == null) return;
    const controller = new AbortController();
    const fail = (err: unknown) => {
      if (controller.signal.aborted) return;
      const status = err instanceof ResearchApiError ? err.status : 0;
      setState({ key, status: status === 503 ? "not-configured" : status === 404 ? "no-match" : "failed" });
    };
    if (isBusiness) {
      fetchPlaceProfile(name, latitude, longitude, location.city, controller.signal)
        .then((profile) => setState({ key, status: "profile", profile, others: [] }))
        .catch(fail);
    } else {
      fetchPopularPlaces(latitude, longitude, controller.signal)
        .then(async (places) => {
          const anchor = places.find((place) => place.distance_m <= 80 && sameName(place.name, name));
          if (anchor) {
            try {
              const profile = await fetchPlaceProfile(anchor.name, anchor.latitude, anchor.longitude, location.city, controller.signal);
              setState({ key, status: "profile", profile, others: places.filter((place) => place !== anchor) });
              return;
            } catch {
              if (controller.signal.aborted) return;
            }
          }
          setState({ key, status: "popular", places });
        })
        .catch(fail);
    }
    return () => controller.abort();
  }, [key, isBusiness, name, latitude, longitude, location.city]);

  return state?.key === key ? state : null;
}

/** "Open now" (or "Closed now", or just "Opening hours") beside the review count; it opens a small window with the week. */
function OpeningHours({ lines, openNow }: { lines: string[]; openNow: boolean | null }) {
  if (lines.length === 0 && openNow == null) return null;
  const label = openNow == null ? "Opening hours" : openNow ? "Open now" : "Closed now";
  const tone = openNow == null ? "text-[var(--text-muted)]" : openNow ? "text-[var(--supported)]" : "text-[var(--contradicted)]";
  if (lines.length === 0) return <span className={`text-xs font-medium ${tone}`}>{label}</span>;
  return (
    <Popover>
      <PopoverButton
        className={`group flex items-center gap-1 rounded-full px-1.5 py-0.5 text-xs font-medium outline-none transition-colors hover:bg-[var(--bg)] data-[focus]:ring-2 data-[focus]:ring-violet-500 ${tone}`}
      >
        <ClockIcon className="h-3.5 w-3.5" aria-hidden="true" />
        {label}
        <ChevronDownIcon className="h-3 w-3 transition-transform group-data-[open]:rotate-180" aria-hidden="true" />
      </PopoverButton>
      <PopoverPanel
        anchor={{ to: "bottom start", gap: 6 }}
        transition
        className="z-50 w-64 rounded-xl border border-[var(--border)] bg-[var(--bg-alt)] p-3.5 shadow-xl transition duration-150 ease-out data-[closed]:scale-95 data-[closed]:opacity-0"
      >
        <p className="m-0 mb-2 text-[10.5px] font-semibold tracking-wide text-[var(--text-muted)] uppercase">Opening hours</p>
        <ul className="m-0 flex list-none flex-col gap-1 p-0 text-xs">
          {lines.map((line) => {
            const split = line.indexOf(":");
            const day = split > 0 && split < 14 ? line.slice(0, split) : "";
            const hours = day ? line.slice(split + 1).trim() : line;
            return (
              <li key={line} className="flex justify-between gap-3">
                {day && <span className="font-medium text-[var(--text-h)]">{day}</span>}
                <span className="text-right text-[var(--text)]">{hours}</span>
              </li>
            );
          })}
        </ul>
        <p className="m-0 mt-2.5 text-[10.5px] text-[var(--text-muted)]">From Google Maps. Hours can change; check before you go.</p>
      </PopoverPanel>
    </Popover>
  );
}

/** The body of the Google Maps tab: Google's own data for the pin, always Google's and always labeled. */
export function GoogleMapsBody({ current }: { current: GoogleState | null }) {
  if (!current) return <p className={NOTE}>Asking Google Maps…</p>;

  if (current.status === "not-configured") {
    return (
      <p className={NOTE}>
        Google Maps ratings and reviews aren't connected, so review coverage comes only from what the open web surfaced. Add{" "}
        <code>GOOGLE_PLACES_API_KEY</code> to <code>backend/.env</code> to connect them.
      </p>
    );
  }
  if (current.status === "no-match") return <p className={NOTE}>Google Maps has no listing matching this place within a few hundred meters of the pin.</p>;
  if (current.status === "failed") return <p className={NOTE}>The Google Maps lookup failed just now, so its ratings aren't shown.</p>;

  if (current.status === "popular") {
    if (current.places.length === 0) return <p className={NOTE}>Google Maps has no rated places within a short walk of this pin.</p>;
    return (
      <div className="flex flex-col gap-2.5">
        <p className="m-0 text-xs leading-relaxed text-[var(--text-muted)]">
          This pin is an area, not one place, so here are the best-known places around it with Google's own ratings. Name one in your
          question to research it.
        </p>
        <ul className="m-0 flex list-none flex-col divide-y divide-[var(--border)] p-0">
          {current.places.map((place) => (
            <li key={`${place.name}-${place.distance_m}`} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
              <div className="min-w-0">
                <p className="m-0 truncate text-[13px] font-semibold text-[var(--text-h)]" dir="auto">
                  {place.name}
                </p>
                <p className="m-0 text-[11px] text-[var(--text-muted)]">
                  {place.category} · {place.distance_m} m
                </p>
              </div>
              <div className="flex flex-shrink-0 items-center gap-2 text-xs text-[var(--text)]">
                <span className="flex items-center gap-1 font-semibold">
                  <StarIcon className="h-3.5 w-3.5 text-amber-500" aria-hidden="true" />
                  {place.rating.toFixed(1)}
                </span>
                {place.review_count != null && <span className="text-[var(--text-muted)]">{place.review_count.toLocaleString()}</span>}
                {place.maps_url && (
                  <a href={place.maps_url} target="_blank" rel="noreferrer" aria-label={`${place.name} on Google Maps`} className="text-[var(--text-muted)] hover:text-[var(--accent)]">
                    <ArrowTopRightOnSquareIcon className="h-3.5 w-3.5" aria-hidden="true" />
                  </a>
                )}
              </div>
            </li>
          ))}
        </ul>
        <p className="m-0 text-[10.5px] text-[var(--text-muted)]">Source: Google Maps ratings and review counts, shown live.</p>
      </div>
    );
  }

  const p = current.profile;
  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5">
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          {p.rating != null && <span className="text-2xl font-bold tracking-tight text-[var(--text-h)]">{p.rating.toFixed(1)}</span>}
          {p.rating != null && <Stars value={p.rating} />}
          {p.review_count != null && <span className="text-xs text-[var(--text-muted)]">{p.review_count.toLocaleString()} reviews</span>}
          <OpeningHours lines={p.opening_hours} openNow={p.open_now} />
          {p.price_level && <span className="text-xs text-[var(--text-muted)]">· {p.price_level}</span>}
        </div>
        {p.maps_url && (
          <a href={p.maps_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs font-semibold">
            View on Google Maps <ArrowTopRightOnSquareIcon className="h-3 w-3" aria-hidden="true" />
          </a>
        )}
      </div>

      {p.summary && <p className="m-0 text-xs text-[var(--text-muted)]">{p.summary}</p>}

      {p.review_summary && (
        <div className="rounded-xl bg-[var(--bg)] p-3.5">
          <p className="m-0 mb-1 text-[10.5px] font-semibold tracking-wide text-[var(--text-muted)] uppercase">What reviewers mention</p>
          <p className="m-0 text-[13px] leading-relaxed text-[var(--text)]">{p.review_summary}</p>
          <p className="m-0 mt-1.5 text-[10.5px] text-[var(--text-muted)]">
            {p.review_summary_disclosure ?? "AI-generated by Google"}, not a reviewer's words.
            {p.review_summary_report_url && (
              <>
                {" "}
                <a href={p.review_summary_report_url} target="_blank" rel="noreferrer">
                  Report
                </a>
              </>
            )}
          </p>
        </div>
      )}

      {p.reviews.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="m-0 text-[10.5px] font-semibold tracking-wide text-[var(--text-muted)] uppercase">
            Reviews{p.reviews.length > 1 ? ` · scroll for all ${p.reviews.length}` : ""}
          </p>
          {/* Every review, in full, in a list that scrolls with a bar you can see, rather than behind a "show more". */}
          <div
            role="region"
            aria-label="Google Maps reviews"
            tabIndex={0}
            className="scroll-visible flex max-h-72 flex-col gap-2 overflow-y-auto rounded-xl pr-2 outline-none focus-visible:ring-2 focus-visible:ring-violet-500"
          >
            {p.reviews.map((review, i) => (
              <figure key={i} className="m-0 flex-shrink-0 rounded-xl border border-[var(--border)] bg-[var(--bg)] p-3">
                <div className="mb-1 flex items-center justify-between gap-2 text-[11px] text-[var(--text-muted)]">
                  <span className="flex min-w-0 items-center gap-1.5">
                    {review.rating != null && <Stars value={review.rating} />}
                    <span className="truncate">{review.author}</span>
                  </span>
                  {review.published_at && (
                    <span title={absoluteTimeFrom(review.published_at)} className="flex-shrink-0">
                      {relativeTimeFrom(review.published_at)}
                    </span>
                  )}
                </div>
                <blockquote className="m-0 text-xs leading-relaxed text-[var(--text)]">{review.text}</blockquote>
                {review.original_text && review.original_language && (
                  <details className="mt-1.5 text-[11px] text-[var(--text-muted)]">
                    <summary className="cursor-pointer">
                      Translated from {languageNames.of(review.original_language) ?? review.original_language}: show original
                    </summary>
                    <p className="m-0 mt-1" lang={review.original_language} dir="auto">
                      {review.original_text}
                    </p>
                  </details>
                )}
              </figure>
            ))}
          </div>
        </div>
      )}

      {current.others.length > 0 && (
        <details className="text-xs text-[var(--text-muted)]">
          <summary className="cursor-pointer">Also popular nearby ({current.others.length})</summary>
          <ul className="m-0 mt-1.5 flex list-none flex-col gap-1 p-0">
            {current.others.map((place) => (
              <li key={`${place.name}-${place.distance_m}`} className="flex items-center justify-between gap-3">
                <span className="truncate text-[var(--text)]" dir="auto">
                  {place.name} <span className="text-[var(--text-muted)]">· {place.distance_m} m</span>
                </span>
                <span className="flex-shrink-0">
                  ★ {place.rating.toFixed(1)}
                  {place.review_count != null && ` (${place.review_count.toLocaleString()})`}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}

      <p className="m-0 text-[10.5px] text-[var(--text-muted)]">
        Source: Google Maps.{" "}
        {p.reviews.length > 0
          ? `Showing ${p.reviews.length} of ${p.review_count?.toLocaleString() ?? "the listed"} reviews (Google returns at most 5); the rating reflects all of them.`
          : "Google returned no review texts for this place, so the rating and its summary stand in."}
      </p>
    </div>
  );
}
