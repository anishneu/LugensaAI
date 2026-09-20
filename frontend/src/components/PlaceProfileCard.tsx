import { useEffect, useState } from "react";
import { fetchPlaceProfile, ResearchApiError } from "../api";
import { absoluteTimeFrom, relativeTimeFrom } from "../textUtils";
import type { ActiveLocation, PlaceProfile } from "../types";

type ProfileState =
  | { key: string; status: "ready"; profile: PlaceProfile }
  | { key: string; status: "not-configured" | "no-match" | "failed" };

const languageNames = new Intl.DisplayNames(["en"], { type: "language" });

function Stars({ value }: { value: number }) {
  const full = Math.round(value);
  return (
    <span className="tracking-tight text-amber-500" aria-label={`${value} out of 5`}>
      {"★".repeat(full)}
      <span className="text-[var(--border)]">{"★".repeat(Math.max(0, 5 - full))}</span>
    </span>
  );
}

/** What Google Maps lists for one specific business: rating, hours, and real
 * dated reviews. Shown only for a business (not an area), live and attributed
 * to Google. When the server isn't connected to Google, this says so plainly
 * instead of leaving the page looking complete. */
export function PlaceProfileCard({ location }: { location: ActiveLocation }) {
  const { latitude, longitude, isBusiness } = location;
  const name = location.displayName.split(",")[0].trim();
  const key = isBusiness && latitude != null && longitude != null ? `${name}|${latitude},${longitude}` : "";
  const [state, setState] = useState<ProfileState | null>(null);

  useEffect(() => {
    if (!key || latitude == null || longitude == null) return;
    const controller = new AbortController();
    fetchPlaceProfile(name, latitude, longitude, location.city, controller.signal)
      .then((profile) => setState({ key, status: "ready", profile }))
      .catch((err) => {
        if (controller.signal.aborted) return;
        const status = err instanceof ResearchApiError ? err.status : 0;
        setState({ key, status: status === 503 ? "not-configured" : status === 404 ? "no-match" : "failed" });
      });
    return () => controller.abort();
  }, [key, name, latitude, longitude, location.city]);

  if (!key) return null;
  const current = state?.key === key ? state : null;
  if (!current) return null;

  const note = "mx-5 mt-4 rounded-2xl border border-dashed border-[var(--border)] px-4 py-2.5 text-xs text-[var(--text-muted)]";

  if (current.status === "not-configured") {
    return (
      <p className={`${note} m-0`}>
        ⭐ Google Maps ratings and reviews aren't connected, so review coverage of this business comes only from
        what the open web surfaced, which is often thin. Add <code>GOOGLE_PLACES_API_KEY</code> to{" "}
        <code>backend/.env</code> to connect them.
      </p>
    );
  }
  if (current.status === "no-match") {
    return <p className={`${note} m-0`}>Google Maps has no listing matching this business within a few hundred meters of the pin.</p>;
  }
  if (current.status === "failed") {
    return <p className={`${note} m-0`}>The Google Maps lookup failed just now, so its rating and reviews aren't shown.</p>;
  }

  if (current.status !== "ready") return null;
  const p = current.profile;
  return (
    <section className="mx-5 mt-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-alt)] px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex flex-wrap items-baseline gap-x-2.5">
          <h3 className="m-0 text-sm font-bold text-[var(--text-h)]">⭐ On Google Maps</h3>
          {p.rating != null && (
            <span className="text-sm text-[var(--text)]">
              <strong>{p.rating.toFixed(1)}</strong> <Stars value={p.rating} />
              {p.review_count != null && (
                <span className="text-xs text-[var(--text-muted)]"> · {p.review_count.toLocaleString()} reviews</span>
              )}
            </span>
          )}
          {p.price_level && <span className="text-xs text-[var(--text-muted)]">{p.price_level}</span>}
          {p.open_now != null && (
            <span className={`text-xs ${p.open_now ? "text-[var(--supported)]" : "text-[var(--text-muted)]"}`}>
              {p.open_now ? "Open now" : "Closed now"}
            </span>
          )}
        </div>
        {p.maps_url && (
          <a href={p.maps_url} target="_blank" rel="noreferrer" className="text-xs font-semibold">
            View on Google Maps →
          </a>
        )}
      </div>

      {p.summary && <p className="m-0 mt-1.5 text-xs text-[var(--text)]">{p.summary}</p>}
      {p.review_summary && (
        <div className="mt-2 rounded-xl border border-[var(--border)] bg-[var(--bg)] p-3">
          <p className="m-0 mb-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            What Google says reviewers mention{p.review_count ? ` (${p.review_count.toLocaleString()} reviews)` : ""}
          </p>
          <p className="m-0 text-xs leading-relaxed text-[var(--text)]">{p.review_summary}</p>
          <p className="m-0 mt-1.5 text-[10.5px] text-[var(--text-muted)]">
            {p.review_summary_disclosure ?? "AI-generated by Google"} — Google's summary, not a reviewer's words.
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
      {p.opening_hours.length > 0 && (
        <details className="mt-1.5 text-xs text-[var(--text-muted)]">
          <summary className="cursor-pointer">Opening hours</summary>
          <ul className="m-0 mt-1 list-none p-0">
            {p.opening_hours.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </details>
      )}

      {p.reviews.length > 0 && (
        <div className="mt-2.5 flex snap-x snap-mandatory gap-3 overflow-x-auto pb-0.5">
          {p.reviews.map((review, i) => (
            <figure
              key={i}
              className="m-0 w-72 flex-shrink-0 snap-start rounded-xl border border-[var(--border)] bg-[var(--bg)] p-3"
            >
              <div className="mb-1 flex items-center justify-between gap-2 text-[11px] text-[var(--text-muted)]">
                <span className="truncate">
                  {review.rating != null && <Stars value={review.rating} />} {review.author}
                </span>
                {review.published_at && (
                  <span title={absoluteTimeFrom(review.published_at)} className="flex-shrink-0">
                    {relativeTimeFrom(review.published_at)}
                  </span>
                )}
              </div>
              <blockquote className="m-0 line-clamp-5 text-xs leading-relaxed text-[var(--text)]">
                {review.text}
              </blockquote>
              {review.original_text && review.original_language && (
                <details className="mt-1.5 text-[11px] text-[var(--text-muted)]">
                  <summary className="cursor-pointer">
                    Translated from {languageNames.of(review.original_language) ?? review.original_language} — show original
                  </summary>
                  <p className="m-0 mt-1" lang={review.original_language} dir="auto">
                    {review.original_text}
                  </p>
                </details>
              )}
            </figure>
          ))}
        </div>
      )}

      <p className="m-0 mt-2 text-[10.5px] text-[var(--text-muted)]">
        {p.reviews.length > 0
          ? `Source: Google Maps. Showing ${p.reviews.length} of ${p.review_count?.toLocaleString() ?? "the listed"} reviews (Google's API returns at most 5), so the rating reflects all of them and the quotes only some.`
          : "Source: Google Maps. Google didn't return individual review texts for this place, so the rating and Google's summary are shown instead."}
      </p>
    </section>
  );
}
