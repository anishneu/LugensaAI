import { useEffect, useMemo, useState } from "react";
import type { ComponentType, SVGProps } from "react";
import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from "@headlessui/react";
import {
  ArrowTopRightOnSquareIcon,
  BanknotesIcon,
  CakeIcon,
  ChevronRightIcon,
  ClockIcon,
  GlobeAltIcon,
  HeartIcon,
  LanguageIcon,
  MapPinIcon,
  PhoneIcon,
  ShieldCheckIcon,
  ShoppingBagIcon,
  TruckIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import { fetchNearby, translateTexts } from "../../api";
import { placeMapsUrl } from "../../maps";
import type { ActiveLocation, NearbyGroup, NearbyItem, NearbyPlaces } from "../../types";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

const GROUP_ICON: Record<string, Icon> = {
  "Food & drink": CakeIcon,
  Transit: TruckIcon,
  "Groceries & convenience": ShoppingBagIcon,
  Health: HeartIcon,
  Safety: ShieldCheckIcon,
  Money: BanknotesIcon,
};

// What the backend looks at by default (`NEARBY_RADIUS_M`), shown until its answer says otherwise.
const DEFAULT_RADIUS_M = 1000;
const WALKING_METERS_PER_MINUTE = 80;
const WHEELCHAIR: Record<string, string> = { yes: "Step-free access", limited: "Limited step-free access", no: "Not step-free" };

function walkLabel(meters: number): string {
  const minutes = Math.max(1, Math.round(meters / WALKING_METERS_PER_MINUTE));
  return `${meters} m · ~${minutes} min walk`;
}

/** Whether text is in a script other than Latin (Japanese, Cyrillic, Arabic...). Mirrors `has_non_latin_letters` in the backend. */
function needsTranslation(text: string): boolean {
  for (const ch of text) {
    const code = ch.codePointAt(0) ?? 0;
    if (code > 0x24f && /\p{L}/u.test(ch)) return true;
  }
  return false;
}

// Where the local names are English already. Anywhere else, a name in the Latin script (German, French, Polish...) can be
// just as unreadable to a visitor as one in Japanese, so the button is offered for those too.
const ENGLISH_SPEAKING = new Set(["United Kingdom", "United States", "Ireland", "Australia", "New Zealand", "Canada", "Singapore"]);

/** Everything the card shows that could be in another language. Names are offered in any script when the place isn't
 * English-speaking; addresses only when they are in a non-Latin script, because a Latin-script street name ("Neuwerkstraße")
 * is a proper noun that a translation would only spoil. */
function translatable(data: NearbyPlaces, anyScript: boolean): string[] {
  const found = new Set<string>();
  for (const group of data.groups) {
    for (const item of group.nearest) {
      if (item.name && /\p{L}/u.test(item.name) && (anyScript || needsTranslation(item.name))) found.add(item.name);
      if (item.address && needsTranslation(item.address)) found.add(item.address);
    }
  }
  return [...found].slice(0, 120);
}

type Translation =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "on"; map: Record<string, string> }
  | { status: "off"; map: Record<string, string> }
  | { status: "unavailable" | "failed" };

/** A name, shown in English with the original beneath when translation is on. */
function Name({ text, translation, block = false }: { text: string; translation: Translation; block?: boolean }) {
  const english = translation.status === "on" ? translation.map[text] : undefined;
  if (!english) return <span dir="auto">{text}</span>;
  return (
    <>
      <span>{english}</span>
      <span className={`${block ? "block" : "ml-1.5"} text-[10.5px] font-normal text-[var(--text-muted)]`} dir="auto">
        {text}
      </span>
    </>
  );
}

function PlaceRow({ item, translation }: { item: NearbyItem; translation: Translation }) {
  const facts: { icon: Icon; text: string; href?: string; translate?: boolean }[] = [];
  if (item.opening_hours) facts.push({ icon: ClockIcon, text: item.opening_hours });
  if (item.phone) facts.push({ icon: PhoneIcon, text: item.phone, href: `tel:${item.phone.replace(/\s+/g, "")}` });
  if (item.website) facts.push({ icon: GlobeAltIcon, text: item.website.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, ""), href: item.website });
  if (item.address) facts.push({ icon: MapPinIcon, text: item.address, translate: true });

  return (
    <li className="rounded-xl border border-[var(--border)] bg-[var(--bg)] p-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="m-0 text-sm font-semibold text-[var(--text-h)]">
            <Name text={item.name} translation={translation} block />
          </p>
          <p className="m-0 mt-0.5 text-xs text-[var(--text-muted)]">
            {item.kind}
            {item.cuisine ? ` · ${item.cuisine}` : ""} · {walkLabel(item.distance_m)}
          </p>
        </div>
        {item.latitude != null && item.longitude != null && (
          <a
            href={placeMapsUrl({ ...item, latitude: item.latitude, longitude: item.longitude })}
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
          {facts.map(({ icon: FactIcon, text, href, translate }) => (
            <li key={text} className="flex items-start gap-2 text-xs text-[var(--text)]">
              <FactIcon className="mt-px h-3.5 w-3.5 flex-shrink-0 text-[var(--text-muted)]" aria-hidden="true" />
              {href ? (
                <a href={href} target={href.startsWith("http") ? "_blank" : undefined} rel="noopener noreferrer" className="break-all text-[var(--accent)] hover:underline">
                  {text}
                </a>
              ) : (
                <span className="break-words">{translate ? <Name text={text} translation={translation} block /> : text}</span>
              )}
            </li>
          ))}
          {item.wheelchair && <li className="text-[11px] text-[var(--text-muted)]">♿ {WHEELCHAIR[item.wheelchair] ?? item.wheelchair}</li>}
        </ul>
      )}
    </li>
  );
}

function GroupDialog({
  group,
  open,
  radius,
  translation,
  onClose,
}: {
  group: NearbyGroup | null;
  open: boolean;
  radius: number;
  translation: Translation;
  onClose: () => void;
}) {
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
                  <PlaceRow key={`${item.name}-${item.distance_m}`} item={item} translation={translation} />
                ))}
              </ul>
              <p className="m-0 border-t border-[var(--border)] px-5 py-3 text-[11px] leading-relaxed text-[var(--text-muted)]">
                From OpenStreetMap volunteers, not AI. Hours, phone numbers and websites appear only where someone added them to the
                map, and may be out of date.
                {translation.status === "on" && " English names are machine translations: a gloss, not an official name."}
              </p>
            </>
          )}
        </DialogPanel>
      </div>
    </Dialog>
  );
}

/** What's physically around the pin, straight from OpenStreetMap map data: listed features with computed distances, not
 * text a model summarized, so this is the part to trust for "is there a bar / station / pharmacy nearby". A compact grid
 * of categories, each opening a dialog with every place and what the map knows about it. Names in another script can
 * be translated to English on request (any script, when the place isn't English-speaking). */
export function NearbyTab({ location, onSummary }: { location: ActiveLocation; onSummary?: (summary: string) => void }) {
  const { latitude, longitude } = location;
  const key = latitude != null && longitude != null ? `${latitude},${longitude}` : "";
  const [state, setState] = useState<{ key: string; data: NearbyPlaces | null } | null>(null);
  // Bumped by "Try again": the public map servers are sometimes busy, and a second attempt often succeeds.
  const [attempt, setAttempt] = useState(0);
  // The group stays selected while the dialog fades out, so its content doesn't empty before it disappears.
  const [selected, setSelected] = useState<NearbyGroup | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [translation, setTranslation] = useState<Translation>({ status: "idle" });

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
  const anyScript = location.country != null && !ENGLISH_SPEAKING.has(location.country);
  const foreign = useMemo(() => (data ? translatable(data, anyScript) : []), [data, anyScript]);

  // The tab shows this beside its name, so the count is readable without opening the tab.
  useEffect(() => {
    if (!settled) onSummary?.("Looking up…");
    else if (!data) onSummary?.("Unavailable");
    else if (data.groups.length === 0) onSummary?.("None listed");
    else onSummary?.(`${data.groups.reduce((sum, g) => sum + g.total, 0)} places`);
  }, [settled, data, onSummary]);

  async function toggleTranslation() {
    if (translation.status === "on") return setTranslation({ status: "off", map: translation.map });
    if (translation.status === "off") return setTranslation({ status: "on", map: translation.map });
    if (latitude == null || longitude == null) return;
    setTranslation({ status: "loading" });
    try {
      const result = await translateTexts(latitude, longitude, foreign);
      if (!result.available) return setTranslation({ status: "unavailable" });
      const map: Record<string, string> = {};
      foreign.forEach((text, i) => {
        const english = result.translations[i];
        if (english) map[text] = english;
      });
      // Nothing translated at all usually means the language pack was still being downloaded on first use.
      setTranslation(Object.keys(map).length > 0 ? { status: "on", map } : { status: "failed" });
    } catch {
      setTranslation({ status: "failed" });
    }
  }

  if (!key) return null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span
          className="text-[11px] text-[var(--text-muted)]"
          title="Ratings, reviews and opening status aren't reliably in map data. Those come from Google Maps and the web sources in the answer."
        >
          OpenStreetMap · within {data?.radius_m ?? DEFAULT_RADIUS_M} m · not AI-generated
        </span>
        {foreign.length > 0 && (
          <button
            type="button"
            onClick={toggleTranslation}
            disabled={translation.status === "loading"}
            className="flex items-center gap-1.5 rounded-full border border-[var(--border)] px-3 py-1 text-[11px] font-medium text-[var(--text)] transition hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:cursor-wait disabled:opacity-60"
          >
            <LanguageIcon className="h-3.5 w-3.5" aria-hidden="true" />
            {translation.status === "loading" ? "Translating…" : translation.status === "on" ? "Show originals" : "Translate to English"}
          </button>
        )}
      </div>

      {translation.status === "unavailable" && (
        <p className="m-0 text-[11px] text-[var(--text-muted)]">
          Translation isn't available for this place: the free translator has no pack for its language, or it is turned off.
        </p>
      )}
      {translation.status === "failed" && <p className="m-0 text-[11px] text-[var(--contradicted)]">No English translation could be made just now (the first use of a language downloads its pack). Try again in a minute.</p>}
      {translation.status === "on" && (
        <p className="m-0 text-[11px] text-[var(--text-muted)]">English names are machine translations, with the original beneath.</p>
      )}

      {!settled && <p className="m-0 text-xs text-[var(--text-muted)]">Looking up what's nearby…</p>}

      {settled && !data && (
        <p className="m-0 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-[var(--text-muted)]">
          <span>
            Map data is unavailable right now (the public OpenStreetMap servers were busy). That doesn't mean nothing is nearby.
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
          OpenStreetMap lists no named food, transit, shops, health, safety, or banking places within {data.radius_m} m of this pin. Map
          coverage varies by area, so this may reflect gaps in the map.
        </p>
      )}

      {data && data.groups.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {data.groups.map((group) => {
            const GroupIcon = GROUP_ICON[group.label] ?? MapPinIcon;
            const nearest = group.nearest[0];
            return (
              <button
                key={group.label}
                type="button"
                onClick={() => {
                  setSelected(group);
                  setDialogOpen(true);
                }}
                className="group flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--bg)] p-3 text-left transition-colors hover:border-[var(--accent)] focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none"
              >
                <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-[var(--accent-bg)] text-[var(--accent)]">
                  <GroupIcon className="h-5 w-5" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline justify-between gap-2">
                    <span className="text-[13px] font-bold text-[var(--text-h)]">{group.label}</span>
                    <span className="text-[10.5px] text-[var(--text-muted)]">{group.total}</span>
                  </span>
                  <span className="block truncate text-[11.5px] text-[var(--text)]">
                    <Name text={nearest.name} translation={translation} />
                  </span>
                  <span className="block text-[10.5px] text-[var(--text-muted)]">
                    nearest · {nearest.distance_m} m
                  </span>
                </span>
                <ChevronRightIcon className="h-4 w-4 flex-shrink-0 text-[var(--text-muted)] transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
              </button>
            );
          })}
        </div>
      )}

      <GroupDialog group={selected} open={dialogOpen} radius={data?.radius_m ?? DEFAULT_RADIUS_M} translation={translation} onClose={() => setDialogOpen(false)} />
    </div>
  );
}
