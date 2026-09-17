import { useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { LocationSuggestion } from "../types";

interface LocationSearchInputProps {
  value: string;
  onChange: (value: string) => void;
  suggestions: LocationSuggestion[];
  onSelect: (suggestion: LocationSuggestion) => void;
  onSubmit: (text: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
}

function matches(suggestion: LocationSuggestion, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return (
    suggestion.name.toLowerCase().includes(q) ||
    (suggestion.city ?? "").toLowerCase().includes(q) ||
    suggestion.aliases.some((alias) => alias.toLowerCase().includes(q))
  );
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
  const containerRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => suggestions.filter((s) => matches(s, value)).slice(0, 6), [suggestions, value]);

  function selectSuggestion(suggestion: LocationSuggestion) {
    onSelect(suggestion);
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
      setHighlighted((i) => Math.min(i + 1, filtered.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (open && highlighted >= 0 && filtered[highlighted]) {
        selectSuggestion(filtered[highlighted]);
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
        placeholder={placeholder ?? "Search a location…"}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setHighlighted(-1);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onKeyDown={handleKeyDown}
      />
      {open && filtered.length > 0 && (
        <ul className="location-suggestions">
          {filtered.map((suggestion, i) => (
            <li key={suggestion.raw_query}>
              <button
                type="button"
                className={i === highlighted ? "active" : ""}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => selectSuggestion(suggestion)}
              >
                <span className="suggestion-pin" aria-hidden="true">
                  📍
                </span>
                <span>
                  <strong>{suggestion.name}</strong>
                  {suggestion.city ? `, ${suggestion.city}` : ""}
                  {suggestion.region ? `, ${suggestion.region}` : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
