import { useCallback, useEffect, useRef, useState } from "react";
import type { ComponentType, SVGProps } from "react";
import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from "@headlessui/react";
import {
  ArrowTopRightOnSquareIcon,
  BanknotesIcon,
  CakeIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClockIcon,
  GlobeAltIcon,
  HeartIcon,
  MapPinIcon,
  PhoneIcon,
  ShieldCheckIcon,
  ShoppingBagIcon,
  TruckIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import { fetchNearby } from "../api";
import type { ActiveLocation, NearbyGroup, NearbyItem, NearbyPlaces } from "../types";
import { googleMapsUrl } from "../maps";

interface NearbyState {
  key: string;
  data: NearbyPlaces | null;
}

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

const GROUP_ICON: Record<string, Icon> = {
  "Food & drink": CakeIcon,
  Transit: TruckIcon,
  "Groceries & convenience": ShoppingBagIcon,
  Health: HeartIcon,
  Safety: ShieldCheckIcon,
  Money: BanknotesIcon,
};

const WALKING_METERS_PER_MINUTE = 80;
const PREVIEW_ITEMS = 3;

function walkLabel(meters: number): string {
  const minutes = Math.max(1, Math.round(meters / WALKING_METERS_PER_MINUTE));
  return `${meters} m · ~${minutes} min walk`;
}

const WHEELCHAIR: Record<string, string> = { yes: "Step-free access", limited: "Limited step-free access", no: "Not step-free" };

/** One place, with everything OpenStreetMap knows about it. A missing field is just missing from the map. */
function PlaceRow({ item }: { item: NearbyItem }) {
  const facts: { icon: Icon; text: string; href?: string }[] = [];
  if (item.opening_hours) facts.push({ icon: ClockIcon, text: item.opening_hours });
  if (item.phone) facts.push({ icon: PhoneIcon, text: item.phone, href: `tel:${item.phone.replace(/\s+/g, "")}` });
  if (item.website) facts.push({ icon: GlobeAltIcon, text: item.website.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, ""), href: item.website });
  if (item.address) facts.push({ icon: MapPinIcon, text: item.address });

  return (
    <li className="rounded-xl border border-[var(--border)] bg-[var(--bg)] p-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="m-0 text-sm font-semibold text-[var(--text-h)]" dir="auto">
            {item.name}
          </p>
          <p className="m-0 mt-0.5 text-xs text-[var(--text-muted)]">
            {item.kind}
            {item.cuisine ? ` · ${item.cuisine}` : ""} · {walkLabel(item.distance_m)}
          </p>
        </div>
        {item.latitude != null && item.longitude != null && (
          <a
            href={googleMapsUrl(item.latitude, item.longitude)}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-shrink-0 items-center gap-1 rounded-full border border-[var(--border)] px-2.5 py-1 text-[11px] font-medium text-[var(--text)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            Map
            <ArrowTopRightOnSquareIcon className="h-3 w-3" aria-hidden="true" />
          </a>
        )}
      </div>

      {(facts.length > 0 || item.wheelchair) && (
        <ul className="m-0 mt-2.5 flex list-none flex-col gap-1.5 p-0">
          {facts.map(({ icon: FactIcon, text, href }) => (
            <li key={text} className="flex items-start gap-2 text-xs text-[var(--text)]">
              <FactIcon className="mt-px h-3.5 w-3.5 flex-shrink-0 text-[var(--text-muted)]" aria-hidden="true" />
              {href ? (
                <a href={href} target={href.startsWith("http") ? "_blank" : undefined} rel="noopener noreferrer" className="break-all text-[var(--accent)] hover:underline">
                  {text}
                </a>
              ) : (
                <span className="break-words">{text}</span>
              )}
            </li>
          ))}
          {item.wheelchair && (
            <li className="text-[11px] text-[var(--text-muted)]">♿ {WHEELCHAIR[item.wheelchair] ?? item.wheelchair}</li>
          )}
        </ul>
      )}
    </li>
  );
}

function GroupDialog({ group, open, radius, onClose }: { group: NearbyGroup | null; open: boolean; radius: number; onClose: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} className="relative z-50">
      <DialogBackdrop transition className="fixed inset-0 bg-black/55 backdrop-blur-sm duration-200 ease-out data-[closed]:opacity-0" />
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel
          transition
          className="flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-alt)] shadow-2xl duration-200 ease-out data-[closed]:scale-95 data-[closed]:opacity-0"
        >
          {group && (
            <>
              <div className="flex items-start justify-between gap-4 border-b border-[var(--border)] px-5 py-4">
                <div>
                  <DialogTitle className="m-0 text-base font-bold text-[var(--text-h)]">{group.label}</DialogTitle>
                  <p className="m-0 mt-0.5 text-xs text-[var(--text-muted)]">
                    {group.total} listed within {radius} m
                    {group.total > group.nearest.length ? ` · showing the nearest ${group.nearest.length}` : ""}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Close"
                  className="rounded-full p-1.5 text-[var(--text-muted)] transition hover:bg-[var(--bg)] hover:text-[var(--text-h)] focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none"
                >
                  <XMarkIcon className="h-5 w-5" aria-hidden="true" />
                </button>
              </div>
              <ul className="m-0 flex list-none flex-col gap-2.5 overflow-y-auto p-4">
                {group.nearest.map((item) => (
                  <PlaceRow key={`${item.name}-${item.distance_m}`} item={item} />
                ))}
              </ul>
              <p className="m-0 border-t border-[var(--border)] px-5 py-3 text-[11px] leading-relaxed text-[var(--text-muted)]">
                From OpenStreetMap volunteers, not AI. Hours, phone numbers and websites appear only where someone added
                them to the map, and may be out of date.
              </p>
            </>
          )}
        </DialogPanel>
      </div>
    </Dialog>
  );
}

/** What's physically around the pin, straight from OpenStreetMap map data. Deliberately separate from the agent's
 * answer: these are listed features with computed distances, not text a model summarized from web pages, so this is
 * the part of the page to trust for "is there a bar / station / pharmacy nearby". Each group opens a dialog with
 * every place in it and what the map knows about each. */
export function NearbyCard({ location }: { location: ActiveLocation }) {
  const { latitude, longitude } = location;
  const key = latitude != null && longitude != null ? `${latitude},${longitude}` : "";
  const [state, setState] = useState<NearbyState | null>(null);
  // Bumped by "Try again": the public map servers are sometimes busy, and a second attempt often succeeds.
  const [attempt, setAttempt] = useState(0);
  // The group stays selected while the dialog fades out, so its content doesn't empty before it disappears.
  const [selected, setSelected] = useState<NearbyGroup | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const trackRef = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ start: true, end: true });

  useEffect(() => {
    if (!key || latitude == null || longitude == null) return;
    const controller = new AbortController();
    fetchNearby(latitude, longitude, controller.signal)
      .then((data) => setState({ key, data }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ key, data: null });
      });
    return () => controller.abort();
  }, [key, latitude, longitude, attempt]);

  const settled = state?.key === key;
  const data = settled ? state.data : null;
  const groupCount = data?.groups.length ?? 0;

  const updateEdges = useCallback(() => {
    const el = trackRef.current;
    if (!el) return;
    setEdges({ start: el.scrollLeft <= 2, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 2 });
  }, []);

  useEffect(() => {
    updateEdges();
    window.addEventListener("resize", updateEdges);
    return () => window.removeEventListener("resize", updateEdges);
  }, [groupCount, updateEdges]);

  function slide(direction: 1 | -1) {
    const el = trackRef.current;
    if (el) el.scrollBy({ left: direction * Math.max(el.clientWidth * 0.8, 240), behavior: "smooth" });
  }

  if (!key) return null;

  const arrow =
    "flex h-7 w-7 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--bg)] text-[var(--text)] transition-colors hover:border-[var(--accent)] disabled:cursor-default disabled:opacity-35 disabled:hover:border-[var(--border)]";

  return (
    <section
      className="mx-5 mt-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-alt)] px-4 py-3"
    >
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-3">
          <h3 className="m-0 flex items-center gap-1.5 text-sm font-bold text-[var(--text-h)]">
            <MapPinIcon className="h-4 w-4 text-[var(--accent)]" aria-hidden="true" /> Around this pin
          </h3>
          <span
            className="truncate text-[11px] text-[var(--text-muted)]"
            title="Ratings, reviews and opening status aren't reliably in map data. Those come from the web sources in the answer and Google Maps, and are only as reliable as those sources."
          >
            OpenStreetMap · within {data?.radius_m ?? 600} m · not AI-generated
          </span>
        </div>
        {groupCount > 1 && (
          <div className="flex flex-shrink-0 gap-1.5">
            <button type="button" className={arrow} onClick={() => slide(-1)} disabled={edges.start} aria-label="Previous">
              <ChevronLeftIcon className="h-4 w-4" aria-hidden="true" />
            </button>
            <button type="button" className={arrow} onClick={() => slide(1)} disabled={edges.end} aria-label="Next">
              <ChevronRightIcon className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        )}
      </div>

      {!settled && <p className="m-0 text-xs text-[var(--text-muted)]">Looking up what's nearby…</p>}

      {settled && !data && (
        <p className="m-0 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-[var(--text-muted)]">
          <span>
            Map data is unavailable right now (the public OpenStreetMap servers were busy). That doesn't mean nothing is
            nearby.
          </span>
          <button
            type="button"
            onClick={() => {
              setState(null);
              setAttempt((n) => n + 1);
            }}
            className="rounded-full border border-[var(--border)] px-3 py-1 font-medium text-[var(--text)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            Try again
          </button>
        </p>
      )}

      {data && data.groups.length === 0 && (
        <p className="m-0 text-xs text-[var(--text-muted)]">
          OpenStreetMap lists no named food, transit, shops, health, safety, or banking places within {data.radius_m} m of
          this pin. Map coverage varies by area, so this may reflect gaps in the map.
        </p>
      )}

      {data && data.groups.length > 0 && (
        <div ref={trackRef} onScroll={updateEdges} className="flex snap-x snap-mandatory gap-3 overflow-x-auto scroll-smooth pb-0.5">
          {data.groups.map((group) => {
            const GroupIcon = GROUP_ICON[group.label] ?? MapPinIcon;
            return (
              <button
                key={group.label}
                type="button"
                onClick={() => {
                  setSelected(group);
                  setDialogOpen(true);
                }}
                className="group w-60 flex-shrink-0 snap-start rounded-xl border border-[var(--border)] bg-[var(--bg)] p-3 text-left transition-colors hover:border-[var(--accent)] focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none"
              >
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2 text-xs font-bold text-[var(--text-h)]">
                    <span className="flex h-6 w-6 items-center justify-center rounded-md bg-[var(--accent-bg)] text-[var(--accent)]">
                      <GroupIcon className="h-3.5 w-3.5" aria-hidden="true" />
                    </span>
                    {group.label}
                  </span>
                  <span className="text-[10.5px] text-[var(--text-muted)]">{group.total} listed</span>
                </div>
                <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
                  {group.nearest.slice(0, PREVIEW_ITEMS).map((item) => (
                    <li key={`${item.name}-${item.distance_m}`} className="text-xs leading-snug text-[var(--text)]">
                      <span className="font-medium" dir="auto">
                        {item.name}
                      </span>
                      <span className="block text-[11px] text-[var(--text-muted)]">
                        {item.kind} · {walkLabel(item.distance_m)}
                      </span>
                    </li>
                  ))}
                </ul>
                <span className="mt-2.5 flex items-center gap-1 text-[11px] font-medium text-[var(--accent)]">
                  View all {group.total > group.nearest.length ? group.nearest.length : group.total} and details
                  <ChevronRightIcon className="h-3 w-3 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
                </span>
              </button>
            );
          })}
        </div>
      )}

      <GroupDialog group={selected} open={dialogOpen} radius={data?.radius_m ?? 600} onClose={() => setDialogOpen(false)} />
    </section>
  );
}
