import { useCallback, useEffect, useRef, useState } from "react";
import { GlobeAltIcon, StarIcon } from "@heroicons/react/24/outline";
import { StarIcon as StarSolid } from "@heroicons/react/24/solid";
import { fetchCapabilities } from "../../api";
import type { ActiveLocation } from "../../types";
import { BrowserTabs } from "./BrowserTabs";
import type { BrowserTabItem } from "./BrowserTabs";
import { GoogleMapsBody, useGoogleData } from "./GoogleMapsTab";
import type { GoogleState } from "./GoogleMapsTab";
import { NearbyTab } from "./NearbyTab";

/** What the Google Maps tab says about its content, beside its name. */
function googleBadge(state: GoogleState | null) {
  if (!state) return <span>Asking…</span>;
  if (state.status === "profile") {
    const { rating, review_count } = state.profile;
    if (rating == null) return null;
    return (
      <span className="flex items-center gap-0.5 font-semibold text-[var(--text-h)]">
        <StarSolid className="h-3 w-3 text-amber-500" aria-hidden="true" />
        {rating.toFixed(1)}
        {review_count != null && <span className="ml-0.5 font-normal text-[var(--text-muted)]">({review_count.toLocaleString()})</span>}
      </span>
    );
  }
  if (state.status === "popular") return <span>{state.places.length} nearby</span>;
  if (state.status === "not-configured") return <span>Not connected</span>;
  if (state.status === "no-match") return <span>No listing</span>;
  return <span>Unavailable</span>;
}

/**
 * What is known about the pin itself, in two browser-style tabs: Google Maps' ratings and reviews, and what the map lists
 * around the pin. The Google tab is left out when the server isn't connected to Google. The chevron folds the panel.
 *
 * The Google tab starts with the well-known places around an area. When the answer names or adopts a specific place, that
 * content is replaced by the place's own rating and reviews, and the tab says so: a pulsing dot and an "Updated" mark on
 * the tab itself, and a line inside the tab saying what replaced what. The mark stays until the tab is clicked, and the
 * line until it is dismissed, so the change is not missed while the answer is still arriving. A tab the reader is not on
 * is never switched away from, but a folded panel is opened.
 */
export function PlacePanel({ location }: { location: ActiveLocation }) {
  const [googleAvailable, setGoogleAvailable] = useState<boolean | null>(null);
  const [selected, setSelected] = useState("google");
  const [open, setOpen] = useState(true);
  const [nearbySummary, setNearbySummary] = useState("…");
  // The place whose reviews replaced the area's list: the banner in the tab, and the mark on the tab.
  const [updatedFor, setUpdatedFor] = useState<string | null>(null);
  const [tabMarked, setTabMarked] = useState(false);
  const hasPin = location.latitude != null && location.longitude != null;
  const google = useGoogleData(location);
  // What the Google tab last showed, to tell "replaced by the place's own reviews" from "loaded for the first time".
  const shown = useRef<{ profile: boolean; name: string } | null>(null);

  useEffect(() => {
    fetchCapabilities().then((caps) => setGoogleAvailable(caps ? caps.place_profile : null));
  }, []);

  useEffect(() => {
    if (!google) return;
    const now = { profile: google.status === "profile", name: google.status === "profile" ? google.profile.name : "" };
    const before = shown.current;
    shown.current = now;
    if (!now.profile || !before || (before.profile && before.name === now.name)) return;
    setUpdatedFor(now.name);
    setTabMarked(true);
    setOpen(true);
  }, [google]);

  const onNearbySummary = useCallback((summary: string) => setNearbySummary(summary), []);

  if (!hasPin) return null;
  const showGoogle = googleAvailable !== false;

  const tabs: BrowserTabItem[] = [];
  if (showGoogle) {
    tabs.push({
      id: "google",
      label: "Google Maps",
      icon: <StarIcon className="h-3.5 w-3.5" />,
      badge: googleBadge(google),
      alert: tabMarked,
      content: (
        <>
          {updatedFor && (
            <p className="m-0 mb-3 flex items-start justify-between gap-3 rounded-lg bg-[var(--accent-bg)] px-3 py-2 text-xs leading-relaxed text-[var(--text)]" role="status">
              <span>
                <strong className="text-[var(--accent)]">Updated.</strong> This tab now shows the ratings and reviews for{" "}
                <strong>{updatedFor}</strong>, in place of the popular places near the pin.
              </span>
              <button
                type="button"
                onClick={() => {
                  setUpdatedFor(null);
                  setTabMarked(false);
                }}
                className="flex-shrink-0 border-none bg-transparent p-0 font-semibold text-[var(--accent)] hover:underline"
              >
                Dismiss
              </button>
            </p>
          )}
          <GoogleMapsBody current={google} />
        </>
      ),
    });
  }
  tabs.push({
    id: "nearby",
    label: "Around this pin",
    icon: <GlobeAltIcon className="h-3.5 w-3.5" />,
    badge: <span>{nearbySummary}</span>,
    content: <NearbyTab location={location} onSummary={onNearbySummary} />,
  });

  return (
    <div className="mx-5 mt-4">
      <BrowserTabs
        tabs={tabs}
        selectedId={tabs.some((tab) => tab.id === selected) ? selected : tabs[0].id}
        onSelect={(id) => {
          setSelected(id);
          if (id === "google") setTabMarked(false);
        }}
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (next && selected === "google") setTabMarked(false);
        }}
      />
    </div>
  );
}
