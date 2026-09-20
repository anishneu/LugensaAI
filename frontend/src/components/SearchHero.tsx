import { lazy, Suspense } from "react";
import type { ActiveLocation } from "../types";
import { LocationSearchInput } from "./LocationSearchInput";

// The map library is large and the backdrop is decoration: load it after the page is usable, in its own chunk.
const MapBackdrop = lazy(() => import("./MapBackdrop"));

interface SearchHeroProps {
  query: string;
  onQueryChange: (value: string) => void;
  onSelect: (location: ActiveLocation) => void;
  onSubmit: (text: string) => void;
}

export function SearchHero({ query, onQueryChange, onSelect, onSubmit }: SearchHeroProps) {
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
        </div>
      </div>
    </div>
  );
}
