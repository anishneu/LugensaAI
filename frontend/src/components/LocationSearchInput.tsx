import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { MagnifyingGlassIcon, MapPinIcon } from "@heroicons/react/24/outline";
import { searchPlaces } from "../api";
import type { ActiveLocation, PlaceCandidate } from "../types";

interface LocationSearchInputProps {
  value: string;
  onChange: (value: string) => void;
  onSelect: (location: ActiveLocation) => void;
  onSubmit: (text: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
}

interface SearchOption {
  key: string;
  label: string;
  sublabel: string;
  place: PlaceCandidate;
  toActiveLocation: () => ActiveLocation;
}

/** Suggestions that would read the same on screen are one suggestion: the same name over the same address line. The server already
 * drops repeated full names; this is the guarantee that the list itself never shows two identical rows. */
function withoutLookalikes(options: SearchOption[]): SearchOption[] {
  const seen = new Set<string>();
  return options.filter((option) => {
    const key = `${option.label}|${option.sublabel}`.toLowerCase().replace(/\s+/g, " ").trim();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function placeToOption(place: PlaceCandidate): SearchOption {
  return {
    key: `place:${place.display_name}:${place.latitude}:${place.longitude}`,
    label: place.name,
    sublabel: place.display_name.split(",").slice(1, 4).join(",").trim(),
    place,
    toActiveLocation: () => ({
      rawQuery: place.display_name,
      displayName: `${place.name}${place.city ? `, ${place.city}` : ""}`,
      city: place.city,
      region: place.region,
      country: place.country,
      latitude: place.latitude,
      longitude: place.longitude,
      isBusiness: place.is_business,
      isAddress: place.is_address,
      googlePlaceId: place.google_place_id ?? null,
    }),
  };
}

export function LocationSearchInput({
  value,
  onChange,
  onSelect,
  onSubmit,
  placeholder,
  autoFocus,
}: LocationSearchInputProps) {
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);
  const [liveResults, setLiveResults] = useState<PlaceCandidate[]>([]);
  const [searching, setSearching] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Live place search is debounced and cancellable: every keystroke would otherwise fire a real request.
  useEffect(() => {
    const query = value.trim();
    if (query.length < 3) {
      setLiveResults([]);
      setSearching(false);
      return;
    }
    const controller = new AbortController();
    setSearching(true);
    const timeout = window.setTimeout(() => {
      searchPlaces(query, controller.signal)
        .then((places) => setLiveResults(places))
        .finally(() => setSearching(false));
    }, 350);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [value]);

  const options = useMemo<SearchOption[]>(() => withoutLookalikes(liveResults.map(placeToOption)).slice(0, 8), [liveResults]);

  function selectOption(option: SearchOption) {
    onSelect(option.toActiveLocation());
    setOpen(false);
    setHighlighted(-1);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      setOpen(true);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((i) => Math.min(i + 1, options.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (open && highlighted >= 0 && options[highlighted]) {
        selectOption(options[highlighted]);
      } else if (value.trim()) {
        setOpen(false);
        onSubmit(value.trim());
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const showList = open && (options.length > 0 || searching);

  return (
    <div className="relative w-full" ref={containerRef}>
      <div className="flex items-center gap-3 rounded-2xl border border-white/15 bg-white/[0.07] px-4 py-3.5 shadow-2xl shadow-violet-950/40 backdrop-blur-md transition focus-within:border-violet-300/60 focus-within:bg-white/[0.11]">
        <MagnifyingGlassIcon className="h-5 w-5 flex-shrink-0 text-violet-200" aria-hidden="true" />
        <input
          value={value}
          autoFocus={autoFocus}
          placeholder={placeholder ?? "Search a neighborhood, business, or address…"}
          className="w-full min-w-0 border-none bg-transparent text-base text-white outline-none placeholder:text-white/45"
          onChange={(e) => {
            onChange(e.target.value);
            setOpen(true);
            setHighlighted(-1);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          onKeyDown={handleKeyDown}
          role="combobox"
          aria-expanded={showList}
          aria-autocomplete="list"
        />
        {searching && (
          <span
            className="h-4 w-4 flex-shrink-0 animate-spin rounded-full border-2 border-violet-200/30 border-t-violet-200"
            aria-label="Searching"
          />
        )}
      </div>

      {showList && (
        <ul
          role="listbox"
          className="absolute inset-x-0 top-full z-30 m-0 mt-2 max-h-80 list-none overflow-y-auto rounded-2xl border border-white/15 bg-[#14121f]/95 p-1.5 shadow-2xl backdrop-blur-xl"
        >
          {options.map((option, i) => (
            <li key={option.key} role="option" aria-selected={i === highlighted}>
              <button
                type="button"
                className={`flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left transition ${
                  i === highlighted ? "bg-violet-400/20" : "hover:bg-white/10"
                }`}
                onMouseDown={(e) => e.preventDefault()}
                onMouseEnter={() => setHighlighted(i)}
                onClick={() => selectOption(option)}
              >
                <MapPinIcon className="mt-0.5 h-5 w-5 flex-shrink-0 text-violet-300" aria-hidden="true" />
                <span className="min-w-0 text-sm text-white/90">
                  <strong className="block truncate font-semibold text-white" dir="auto">
                    {option.label}
                  </strong>
                  <span className="block truncate text-xs text-white/55" dir="auto">
                    {option.sublabel}
                  </span>
                </span>
                {option.place.is_business && (
                  <span className="ml-auto flex-shrink-0 self-center rounded-full bg-violet-400/20 px-2 py-0.5 text-[10px] font-medium text-violet-200">
                    {option.place.category}
                  </span>
                )}
              </button>
            </li>
          ))}
          {searching && options.length === 0 && (
            <li className="px-3 py-2.5 text-sm text-white/55">Searching real places…</li>
          )}
        </ul>
      )}
    </div>
  );
}
