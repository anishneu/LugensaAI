import { Popover, PopoverButton, PopoverPanel } from "@headlessui/react";
import { ArrowPathRoundedSquareIcon, MapPinIcon, ScaleIcon, StarIcon, XMarkIcon } from "@heroicons/react/24/outline";
import { StarIcon as StarSolidIcon } from "@heroicons/react/24/solid";
import { useNavigate } from "react-router-dom";
import { placeKey } from "../storage";
import { placeSubtitle } from "../textUtils";
import { TOOLTIP_CLASS } from "./IconButton";
import type { SavedPlace } from "../storage";
import type { ActiveLocation } from "../types";

interface TopNavProps {
  location: ActiveLocation;
  onChangeLocation: () => void;
  /** The viewer's saved places (newest first), whether this one is among them, and how to change the list. */
  saved: SavedPlace[];
  isSaved: boolean;
  onToggleSaved: () => void;
  onOpenSaved: (location: ActiveLocation) => void;
  onRemoveSaved: (key: string) => void;
  onCompare: () => void;
}

const navButton =
  "flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--bg-alt)] px-2.5 py-1.5 sm:px-4 text-[13px] font-medium text-[var(--text-h)] transition-colors hover:border-[var(--accent)] focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none";
// Saved places and Compare are icons alone, their names in a tooltip: round, and the same height as the "Change location" button beside them.
const navIconButton =
  "flex h-[34px] w-[34px] items-center justify-center rounded-full border border-[var(--border)] bg-[var(--bg-alt)] text-[var(--text-h)] transition-colors hover:border-[var(--accent)] focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none";

/** Project title and the place being researched on the left; save, compare and "Change location" on the right. */
export function TopNav({ location, onChangeLocation, saved, isSaved, onToggleSaved, onOpenSaved, onRemoveSaved, onCompare }: TopNavProps) {
  const navigate = useNavigate();
  const subtitle = placeSubtitle(location.displayName, [location.city, location.region, location.country]);

  return (
    <header
      className="sticky top-0 z-40 flex h-14 flex-shrink-0 items-center justify-between gap-4 border-b border-[var(--border)] bg-[var(--bg)]/85 px-4 backdrop-blur-xl sm:px-6"
    >
      <div className="flex min-w-0 items-center gap-2 sm:gap-4">
        <button
          type="button"
          onClick={() => navigate("/")}
          title="Back to the landing page"
          className="flex-shrink-0 rounded-lg px-1 text-lg font-extrabold tracking-tight text-[var(--text-h)] transition hover:opacity-80 focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none"
        >
          Lugensa<span className="text-[var(--accent)]">AI</span>
        </button>

        <span className="hidden h-6 w-px flex-shrink-0 bg-[var(--border)] sm:block" aria-hidden="true" />

        <div className="flex min-w-0 items-center gap-2.5">
          <span className="hidden h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-[var(--accent-bg)] text-[var(--accent)] sm:flex">
            <MapPinIcon className="h-4.5 w-4.5" aria-hidden="true" />
          </span>
          <span className="flex min-w-0 flex-col leading-tight">
            <span className="truncate text-sm font-semibold text-[var(--text-h)]" dir="auto" title={location.displayName}>
              {location.displayName}
            </span>
            {subtitle && (
              <span className="hidden truncate text-[11px] text-[var(--text-muted)] sm:block" dir="auto">
                {subtitle}
              </span>
            )}
          </span>
        </div>
      </div>

      <div className="flex flex-shrink-0 items-center gap-2">
        <Popover className="group relative">
          {({ open }) => (
            <>
          <PopoverButton aria-label={`Saved places (${saved.length})`} className={`${navIconButton} ${isSaved ? "border-amber-400/60 text-amber-400" : ""}`}>
            {isSaved ? <StarSolidIcon className="h-4 w-4" aria-hidden="true" /> : <StarIcon className="h-4 w-4" aria-hidden="true" />}
          </PopoverButton>
          {/* Not while the menu is open: the button keeps focus, and its tooltip would show beside the menu it names. */}
          {!open && (
            <span aria-hidden="true" className={TOOLTIP_CLASS}>
              Saved places{saved.length > 0 ? ` (${saved.length})` : ""}
            </span>
          )}
          <PopoverPanel
            anchor={{ to: "bottom end", gap: 8 }}
            className="z-50 w-[min(20rem,calc(100vw-2rem))] rounded-2xl border border-[var(--border)] bg-[var(--bg)] p-2 shadow-2xl"
          >
            {({ close }) => (
              <div className="flex flex-col gap-1">
                <button
                  type="button"
                  onClick={onToggleSaved}
                  aria-pressed={isSaved}
                  className="flex items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-medium text-[var(--text-h)] transition-colors hover:bg-[var(--bg-alt)] focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none"
                >
                  {isSaved ? <StarSolidIcon className="h-4 w-4 text-amber-400" aria-hidden="true" /> : <StarIcon className="h-4 w-4" aria-hidden="true" />}
                  {isSaved ? "Remove this place from saved" : "Save this place"}
                </button>
                <div className="my-1 h-px bg-[var(--border)]" aria-hidden="true" />
                <p className="m-0 px-3 pt-1 text-[11px] font-semibold tracking-[0.1em] text-[var(--text-muted)] uppercase">Saved places</p>
                {saved.length === 0 ? (
                  <p className="m-0 px-3 py-2 text-xs text-[var(--text-muted)]">Nothing saved yet. They are kept in this browser only.</p>
                ) : (
                  <ul className="m-0 flex max-h-72 list-none flex-col overflow-y-auto p-0">
                    {saved.map((entry) => {
                      const key = placeKey(entry.location);
                      const current = key === placeKey(location);
                      return (
                        <li key={key} className="flex items-center rounded-xl hover:bg-[var(--bg-alt)]">
                          <button
                            type="button"
                            onClick={() => {
                              onOpenSaved(entry.location);
                              close();
                            }}
                            className="min-w-0 flex-1 truncate rounded-xl px-3 py-2 text-left text-sm text-[var(--text)] focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none"
                            dir="auto"
                            title={entry.location.displayName}
                          >
                            {entry.location.displayName}
                            {current && <span className="ml-2 text-[11px] text-[var(--text-muted)]">open now</span>}
                          </button>
                          <button
                            type="button"
                            onClick={() => onRemoveSaved(key)}
                            aria-label={`Remove ${entry.location.displayName} from saved places`}
                            className="mr-1 rounded-full p-1.5 text-[var(--text-muted)] hover:text-[var(--text-h)] focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none"
                          >
                            <XMarkIcon className="h-4 w-4" aria-hidden="true" />
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            )}
          </PopoverPanel>
            </>
          )}
        </Popover>
        <span className="group relative inline-flex">
          <button type="button" onClick={onCompare} aria-label="Compare with another place" className={navIconButton}>
            <ScaleIcon className="h-4 w-4" aria-hidden="true" />
          </button>
          <span aria-hidden="true" className={TOOLTIP_CLASS}>
            Compare with another place
          </span>
        </span>
        <button type="button" onClick={onChangeLocation} aria-label="Change location" className={navButton}>
          <ArrowPathRoundedSquareIcon className="h-4 w-4" aria-hidden="true" />
          <span className="hidden sm:inline">Change location</span>
        </button>
      </div>
    </header>
  );
}
