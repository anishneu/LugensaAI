import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

// One street-level map per city, each drawn once from OpenFreeMap's tiles (OpenStreetMap data): see `assets/backdrops`. Only their
// addresses are collected here (`?url`); a map is downloaded when it is about to be shown, one ahead.
const CITIES = Object.values(
  import.meta.glob<string>("../assets/backdrops/*.webp", { eager: true, query: "?url", import: "default" }),
);

/** How long one map stays before the next fades in: about half of one drift cycle (see `.map-drift`). */
export const SLIDE_MS = 26_000;
/** How long the fade takes: keep in step with `.map-fade-in` in index.css. */
const FADE_MS = 2_500;

interface Direction {
  dx: number;
  dy: number;
}
/** The four ways a map drifts: across, up and down, and along each diagonal. (`dy` is 1.6 where used, so a vertical drift covers about
 * as much ground as a horizontal one on a wide screen.) */
const DIRECTIONS: Direction[] = [
  { dx: 1, dy: 0 },
  { dx: 0, dy: 1.6 },
  { dx: 1, dy: 1.6 },
  { dx: 1, dy: -1.6 },
];

function shuffled<T>(items: T[]): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

interface Slide {
  n: number;
  src: string;
  direction: Direction;
}

/**
 * The search page's backdrop: street maps of different world cities, one after another, each fading into the next and drifting
 * slowly, sometimes across, sometimes up and down, sometimes along a diagonal. They are images and not a live map on purpose: a live map
 * waited on tile requests and WebGL and showed up seconds after the rest of the page, and changing cities meant waiting again. Here the
 * first map is there with the page, and the next is fetched while the current one is on screen, so a change never waits.
 * The order of the maps is shuffled once, and so is the order of the directions, and both are then gone through in turn: every map and
 * every kind of movement comes round before any repeats, and two maps in a row never drift the same way.
 * Someone who has asked for reduced motion gets one still map. The credit for the map data is in `SearchHero`.
 */
export default function MapBackdrop() {
  // Shuffled once, when the page opens (state, not a ref, so the shuffle is not redone on every render).
  const [cities] = useState(() => shuffled(CITIES));
  const [directions] = useState(() => shuffled(DIRECTIONS));
  const slideAt = (n: number): Slide => ({ n, src: cities[n % cities.length], direction: directions[n % directions.length] });
  const [current, setCurrent] = useState<Slide>(() => slideAt(0));
  const [leaving, setLeaving] = useState<Slide | null>(null);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || cities.length < 2) return;
    // Fetch the map that comes next while this one is showing.
    new Image().src = cities[(current.n + 1) % cities.length];
    const change = window.setTimeout(() => {
      setLeaving(current);
      setCurrent(slideAt(current.n + 1));
    }, SLIDE_MS);
    return () => window.clearTimeout(change);
    // `slideAt` only reads the shuffled lists, which never change: the next map is wanted exactly when the current one does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current]);

  // Once the fade is over the map that left is taken away. (Its own effect: the one above re-runs, and cleans up, on every change.)
  useEffect(() => {
    if (!leaving) return;
    const gone = window.setTimeout(() => setLeaving(null), FADE_MS + 200);
    return () => window.clearTimeout(gone);
  }, [leaving]);

  const layer = (s: Slide, role: "current" | "leaving") => (
    <div
      key={s.n}
      data-slide={role}
      className={`absolute inset-0 ${role === "current" && s.n > 0 ? "map-fade-in" : ""}`}
    >
      <img
        src={s.src}
        alt=""
        width={1600}
        height={1000}
        fetchPriority={s.n === 0 ? "high" : "auto"}
        decoding="async"
        style={{ "--dx": s.direction.dx, "--dy": s.direction.dy } as CSSProperties}
        className="map-drift absolute -inset-[9%] h-[118%] w-[118%] max-w-none object-cover"
      />
    </div>
  );

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden bg-[#0b0a14]" aria-hidden="true">
      {leaving && layer(leaving, "leaving")}
      {layer(current, "current")}
    </div>
  );
}
