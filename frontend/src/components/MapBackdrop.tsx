import { useEffect, useRef, useState } from "react";
import { AttributionControl, Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MAP_STYLE } from "../mapSetup";

// The search page's backdrop: a live street map that drifts slowly up and down on its own. It carries no data and implies
// no particular place, so it is a different world city each visit. (The landing page uses a still image instead: see
// `assets/landing-map.webp`.)
const BACKDROP_CITIES: [number, number][] = [
  [139.7005, 35.6595], // Tokyo
  [2.3488, 48.8534], // Paris
  [31.2357, 30.0444], // Cairo
  [36.8219, -1.2921], // Nairobi
  [-46.6333, -23.5505], // Sao Paulo
  [151.2093, -33.8688], // Sydney
  [28.9784, 41.0082], // Istanbul
  [72.8777, 19.076], // Mumbai
  [13.405, 52.52], // Berlin
];

// How far the map travels either side of its start, in degrees of latitude (about 140 px at the zoom used), and how long
// one sweep takes. Slow enough to read as ambience, not as motion to follow.
const DRIFT_DEGREES = 0.02;
const DRIFT_SWEEP_MS = 26_000;

/** A non-interactive map filling its parent. Renders nothing (the page's own background shows) if WebGL is missing. */
export default function MapBackdrop() {
  const container = useRef<HTMLDivElement>(null);
  const wrapper = useRef<HTMLDivElement>(null);
  const [center] = useState(() => BACKDROP_CITIES[Math.floor(Math.random() * BACKDROP_CITIES.length)]);
  // The map is shown once it has drawn its first complete frame. Before that it is only grey (its tiles take a few
  // seconds on a slow connection), which reads as broken; the page's own dark background stands in meanwhile.
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!container.current) return;
    let map: MapLibreMap;
    try {
      map = new MapLibreMap({
        container: container.current,
        style: MAP_STYLE,
        center,
        zoom: 13,
        interactive: false,
        // A dimmed decoration does not need retina sharpness or fade-in blending, and a full-screen canvas at
        // 1.25x-2x pixel density is the expensive part of drawing it.
        pixelRatio: 1,
        fadeDuration: 0,
        attributionControl: false,
      });
      map.addControl(new AttributionControl({ compact: true }), "bottom-right");
    } catch {
      return; // no WebGL: the dark page background stands in
    }
    // The credit starts expanded, which on a phone spans the whole width; fold it to its "i" button (one click away).
    map.once("load", () => {
      setReady(true);
      const credit = container.current?.querySelector(".maplibregl-ctrl-attrib");
      credit?.classList.remove("maplibregl-compact-show");
      credit?.removeAttribute("open");
    });

    // The drift: ease up, then down, then up again, for as long as the page is open. Eased at each turn so it never jerks.
    // Not started for someone who has asked for reduced motion (the map then simply stays where it is); and it is a
    // chain of single moves, each started when the last one ends, so removing the map ends it.
    let direction = 1;
    let removed = false;
    const drift = () => {
      if (removed) return;
      map.easeTo({
        center: [center[0], center[1] + direction * DRIFT_DEGREES],
        duration: DRIFT_SWEEP_MS,
        easing: (t) => -(Math.cos(Math.PI * t) - 1) / 2,
        essential: true,
      });
      direction = -direction;
    };
    const canDrift = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (canDrift) {
      map.once("load", () => {
        map.on("moveend", drift);
        drift();
      });
    }
    return () => {
      removed = true;
      map.off("moveend", drift);
      map.remove();
    };
  }, [center]);

  // The map's own stylesheet gives its element `position: relative` (and, being unlayered, it beats Tailwind's
  // utilities), so the element that fills the page is a wrapper and the map fills that.
  // Off screen, take the map out of compositing altogether: it costs nothing to draw, but a WebGL layer under a
  // scrolling page is still composited on every frame.
  useEffect(() => {
    const el = wrapper.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => {
      el.style.display = entry.isIntersecting ? "" : "none";
    });
    observer.observe(el.parentElement ?? el);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={wrapper}
      className={`pointer-events-none absolute inset-0 transition-opacity duration-1000 motion-reduce:transition-none ${ready ? "opacity-100" : "opacity-0"}`}
      aria-hidden="true"
    >
      <div ref={container} className="h-full w-full" />
    </div>
  );
}
