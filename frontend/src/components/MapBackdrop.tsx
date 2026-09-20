import { useEffect, useRef, useState } from "react";
import { AttributionControl, Map as MapLibreMap } from "maplibre-gl";
import type { ControlPosition } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MAP_STYLE } from "../mapSetup";

// A decorative street-map backdrop, a different world city each visit. It carries no data and implies no
// particular place: the app is not about any one city.
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

/** A non-interactive map filling its parent. Renders nothing (the page's own background shows) if WebGL is missing. */
export default function MapBackdrop({ creditPosition = "bottom-right" }: { creditPosition?: ControlPosition }) {
  const container = useRef<HTMLDivElement>(null);
  const [center] = useState(() => BACKDROP_CITIES[Math.floor(Math.random() * BACKDROP_CITIES.length)]);

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
        attributionControl: false,
      });
      // The credit is required; where it sits is up to the page (the landing page's sits clear of the preview below).
      map.addControl(new AttributionControl({ compact: true }), creditPosition);
    } catch {
      return; // no WebGL: the dark page background stands in
    }
    // The credit starts expanded, which on a phone spans the whole width; fold it to its "i" button (one click away).
    map.once("load", () => {
      const credit = container.current?.querySelector(".maplibregl-ctrl-attrib");
      credit?.classList.remove("maplibregl-compact-show");
      credit?.removeAttribute("open");
    });
    return () => map.remove();
  }, [center, creditPosition]);

  // The map's own stylesheet gives its element `position: relative` (and, being unlayered, it beats Tailwind's
  // utilities), so the element that fills the page is a wrapper and the map fills that.
  return (
    <div className="absolute inset-0" aria-hidden="true">
      <div ref={container} className="h-full w-full" />
    </div>
  );
}
