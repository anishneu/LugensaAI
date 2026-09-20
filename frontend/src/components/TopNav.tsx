import { ArrowPathRoundedSquareIcon, MapPinIcon } from "@heroicons/react/24/outline";
import { useNavigate } from "react-router-dom";
import type { ActiveLocation } from "../types";

interface TopNavProps {
  location: ActiveLocation;
  onChangeLocation: () => void;
}

/** Project title and the place being researched on the left; "Change location" on the right. */
export function TopNav({ location, onChangeLocation }: TopNavProps) {
  const navigate = useNavigate();
  const subtitle = [location.city, location.region, location.country]
    .filter((part, i, all) => part && all.indexOf(part) === i)
    .join(", ");

  return (
    <header
      className="sticky top-0 z-40 flex h-14 flex-shrink-0 items-center justify-between gap-4 border-b border-[var(--border)] bg-[var(--bg)]/85 px-4 backdrop-blur-xl sm:px-6"
    >
      <div className="flex min-w-0 items-center gap-3 sm:gap-4">
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
          <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-[var(--accent-bg)] text-[var(--accent)]">
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

      <button
        type="button"
        onClick={onChangeLocation}
        aria-label="Change location"
        className="flex flex-shrink-0 items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--bg-alt)] px-2.5 py-1.5 sm:px-4 text-[13px] font-medium text-[var(--text-h)] transition-colors hover:border-[var(--accent)] focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none"
      >
        <ArrowPathRoundedSquareIcon className="h-4 w-4" aria-hidden="true" />
        <span className="hidden sm:inline">Change location</span>
      </button>
    </header>
  );
}
