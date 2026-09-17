import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { searchPlaces } from "../api";
import type { ActiveLocation, LocationSuggestion, PlaceCandidate } from "../types";

interface LocationSearchInputProps {
  value: string;
  onChange: (value: string) => void;
  suggestions: LocationSuggestion[];
  onSelect: (location: ActiveLocation) => void;
  onSubmit: (text: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
}

interface SearchOption {
  key: string;
  kind: "known" | "live";
  label: string;
  sublabel: string;
  toActiveLocation: () => ActiveLocation;
}

function matchesFixture(suggestion: LocationSuggestion, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return (
    suggestion.name.toLowerCase().includes(q) ||
    (suggestion.city ?? "").toLowerCase().includes(q) ||
    suggestion.aliases.some((alias) => alias.toLowerCase().includes(q))
  );
}

function fixtureToOption(suggestion: LocationSuggestion): SearchOption {
  return {
    key: `fixture:${suggestion.raw_query}`,
    kind: "known",
    label: suggestion.name,
    sublabel: [suggestion.city, suggestion.region].filter(Boolean).join(", "),
    toActiveLocation: () => ({
      rawQuery: suggestion.raw_query,
      displayName: `${suggestion.name}${suggestion.city ? `, ${suggestion.city}` : ""}`,
      city: suggestion.city,
      region: suggestion.region,
      country: suggestion.country,
      latitude: suggestion.latitude,
      longitude: suggestion.longitude,
    }),
  };
}

function placeToOption(place: PlaceCandidate): SearchOption {
  return {
    key: `place:${place.display_name}:${place.latitude}:${place.longitude}`,
    kind: "live",
    label: place.name,
    sublabel: place.display_name.split(",").slice(1, 4).join(",").trim(),
    toActiveLocation: () => ({
      rawQuery: place.display_name,
      displayName: `${place.name}${place.city ? `, ${place.city}` : ""}`,
      city: place.city,
      region: place.region,
      country: place.country,
      latitude: place.latitude,
      longitude: place.longitude,
    }),
  };
}

export function LocationSearchInput({
  value,
  onChange,
  suggestions,
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

  // Live POI search is debounced and cancellable — every keystroke would
  // otherwise fire a real geocoding request per character typed.
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

  const options = useMemo<SearchOption[]>(() => {
    const fixtureOptions = suggestions.filter((s) => matchesFixture(s, value)).map(fixtureToOption);
    const liveOptions = liveResults.map(placeToOption);
    return [...fixtureOptions, ...liveOptions].slice(0, 8);
  }, [suggestions, liveResults, value]);

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

  return (
    <div className="location-search" ref={containerRef}>
      <span className="location-search-icon" aria-hidden="true">
        🔍
      </span>
      <input
        value={value}
        autoFocus={autoFocus}
        placeholder={placeholder ?? "Search a neighborhood, business, or address…"}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setHighlighted(-1);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onKeyDown={handleKeyDown}
      />
      {open && (options.length > 0 || searching) && (
        <ul className="location-suggestions">
          {options.map((option, i) => (
            <li key={option.key}>
              <button
                type="button"
                className={i === highlighted ? "active" : ""}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => selectOption(option)}
              >
                <span className="suggestion-pin" aria-hidden="true">
                  {option.kind === "known" ? "📍" : "🔎"}
                </span>
                <span>
                  <strong>{option.label}</strong>
                  {option.sublabel ? `, ${option.sublabel}` : ""}
                </span>
              </button>
            </li>
          ))}
          {searching && <li className="suggestion-loading">Searching real places…</li>}
        </ul>
      )}
    </div>
  );
}
