import { lazy, Suspense } from "react";
import { XMarkIcon } from "@heroicons/react/24/outline";
import { StarIcon } from "@heroicons/react/24/solid";
import { placeKey } from "../storage";
import type { SavedPlace } from "../storage";
import type { ActiveLocation } from "../types";
import { LocationSearchInput } from "./LocationSearchInput";

// The map library is large and the backdrop is decoration: load it after the page is usable, in its own chunk.
const MapBackdrop = lazy(() => import("./MapBackdrop"));

interface SearchHeroProps {
  query: string;
  onQueryChange: (value: string) => void;
  onSelect: (location: ActiveLocation) => void;
  onSubmit: (text: string) => void;
  /** A question chosen on the landing page: it waits in the question box once a place is picked. */
  pendingQuestion?: string | null;
  /** Places the viewer saved, newest first, and how to forget one. Kept in this browser only. */
  saved?: SavedPlace[];
  onRemoveSaved?: (key: string) => void;
}

export function SearchHero({ query, onQueryChange, onSelect, onSubmit, pendingQuestion, saved = [], onRemoveSaved }: SearchHeroProps) {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#0b0a14] px-6 py-12 text-white">
      <Suspense fallback={null}>
        <MapBackdrop />
      </Suspense>
      {/* Dims the map so the text reads, and settles into the same dark tone the page starts with. */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-[#0b0a14]/80 via-[#0b0a14]/70 to-[#0b0a14]/90" />

      <div className="relative flex w-full max-w-2xl flex-col gap-6 text-center">
        <p className="m-0 text-xs font-semibold tracking-[0.16em] text-violet-300 uppercase">Lugensa AI · location intelligence</p>
        <h1 className="m-0 text-4xl leading-tight font-semibold tracking-tight text-white sm:text-5xl">Where should the agent investigate?</h1>
        <p className="mx-auto m-0 max-w-xl text-base leading-relaxed text-white/70">
          Any real place, anywhere in the world: a neighborhood, a specific restaurant, an address, or a Google Maps plus code. It
          reads reviews, forums and news in the local language, and answers in English with a source next to every claim.
        </p>
        <div className="mx-auto w-full max-w-xl text-left">
          <LocationSearchInput
            value={query}
            onChange={onQueryChange}
            onSelect={onSelect}
            onSubmit={onSubmit}
            placeholder="Try “Shibuya, Tokyo” or “Le Marais, Paris”…"
            autoFocus
          />
          {pendingQuestion && (
            <p className="mt-3 mb-0 rounded-xl border border-violet-400/30 bg-violet-400/10 px-4 py-2.5 text-sm text-violet-100">
              Pick a place, and this will be ready to ask: <em className="text-white">“{pendingQuestion}”</em>
            </p>
          )}
          {saved.length > 0 && (
            <section aria-label="Saved places" className="mt-5">
              <h2 className="m-0 mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-[0.14em] text-white/55 uppercase">
                <StarIcon className="h-3.5 w-3.5 text-amber-400" aria-hidden="true" />
                Saved places
              </h2>
              <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
                {saved.map((entry) => {
                  const key = placeKey(entry.location);
                  return (
                    <li key={key} className="flex items-center rounded-full border border-white/15 bg-white/[0.07] text-sm text-white/90">
                      <button
                        type="button"
                        onClick={() => onSelect(entry.location)}
                        className="rounded-l-full py-1.5 pr-2 pl-3.5 text-left transition hover:text-white focus-visible:ring-2 focus-visible:ring-violet-400 focus-visible:outline-none"
                        dir="auto"
                      >
                        {entry.location.displayName}
                      </button>
                      <button
                        type="button"
                        onClick={() => onRemoveSaved?.(key)}
                        aria-label={`Remove ${entry.location.displayName} from saved places`}
                        className="rounded-r-full py-1.5 pr-2.5 pl-1 text-white/50 transition hover:text-white focus-visible:ring-2 focus-visible:ring-violet-400 focus-visible:outline-none"
                      >
                        <XMarkIcon className="h-3.5 w-3.5" aria-hidden="true" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
