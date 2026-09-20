import { useEffect, useRef, useState } from "react";
import { Map as MapLibreMap, Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { ArrowTopRightOnSquareIcon, MapPinIcon } from "@heroicons/react/24/outline";
import { MAP_STYLE } from "../mapSetup";
import { googleMapsUrl } from "../maps";
import type { ActiveLocation } from "../types";

const ZOOM = 16.2;

function createPin(): HTMLDivElement {
  const el = document.createElement("div");
  el.className = "relative flex h-9 w-9 items-center justify-center";
  el.innerHTML =
    '<span class="absolute h-9 w-9 animate-ping rounded-full bg-violet-500/40"></span>' +
    '<span class="relative h-4 w-4 rounded-full border-2 border-white bg-violet-600 shadow-lg shadow-violet-900/50"></span>';
  return el;
}

/**
 * The researched place on a zoomed-in map. Clicking the map (not dragging it) opens that spot in Google Maps in a
 * new window, so the pin can be checked against a map you already trust.
 */
export default function MapPanel({ location }: { location: ActiveLocation }) {
  const { latitude, longitude } = location;
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const [failed, setFailed] = useState(false);
  const hasCoords = latitude != null && longitude != null;
  const url = hasCoords ? googleMapsUrl(latitude, longitude) : null;
  // The click handler is attached once, so it reads the current URL from here rather than closing over the first one.
  const urlRef = useRef(url);
  useEffect(() => {
    urlRef.current = url;
  }, [url]);

  // Created once, when the first coordinates arrive; later location changes move the existing map.
  useEffect(() => {
    if (!hasCoords || !container.current || mapRef.current) return;
    let map: MapLibreMap;
    try {
      map = new MapLibreMap({
        container: container.current,
        style: MAP_STYLE,
        center: [longitude, latitude],
        zoom: ZOOM,
        attributionControl: { compact: true },
        scrollZoom: false, // the page must still scroll past it
        doubleClickZoom: false,
        touchZoomRotate: true,
        cooperativeGestures: false,
      });
    } catch {
      setFailed(true); // no WebGL
      return;
    }
    map.on("error", (event) => {
      if (!map.isStyleLoaded()) {
        console.warn("Map style failed to load", event.error);
        setFailed(true);
      }
    });
    // A click, not the end of a drag (MapLibre only emits `click` for a genuine click).
    map.on("click", () => {
      if (urlRef.current) window.open(urlRef.current, "_blank", "noopener,noreferrer");
    });
    // The credit starts expanded and covers a third of a map this small; fold it to its "i" button (still one click away).
    map.once("load", () => {
      const credit = container.current?.querySelector(".maplibregl-ctrl-attrib");
      credit?.classList.remove("maplibregl-compact-show");
      credit?.removeAttribute("open");
    });
    map.getCanvas().style.cursor = "pointer";
    markerRef.current = new Marker({ element: createPin() }).setLngLat([longitude, latitude]).addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      markerRef.current = null;
    };
  }, [hasCoords]);

  useEffect(() => {
    if (!hasCoords || !mapRef.current) return;
    mapRef.current.flyTo({ center: [longitude, latitude], zoom: ZOOM, duration: 900 });
    markerRef.current?.setLngLat([longitude, latitude]);
  }, [hasCoords, latitude, longitude]);

  return (
    <section
      className="group relative h-64 w-full flex-shrink-0 overflow-hidden border-b border-[var(--border)] bg-[var(--bg-alt)]"
      aria-label={`Map of ${location.displayName}`}
    >
      {hasCoords && !failed ? (
        <div ref={container} className="h-full w-full" />
      ) : (
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 px-6 text-center text-sm text-[var(--text-muted)]">
          <MapPinIcon className="h-6 w-6" aria-hidden="true" />
          {hasCoords ? "The map couldn't load (it needs WebGL). The link above still opens it." : "Locating on the map…"}
        </div>
      )}

      {url && (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="absolute top-3 right-3 z-10 flex items-center gap-1.5 rounded-full border border-black/10 bg-white/90 px-3 py-1.5 text-xs font-medium text-slate-800 shadow-md backdrop-blur transition hover:bg-white focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none dark:border-white/15 dark:bg-slate-900/85 dark:text-slate-100 dark:hover:bg-slate-900"
        >
          Open in Google Maps
          <ArrowTopRightOnSquareIcon className="h-3.5 w-3.5" aria-hidden="true" />
        </a>
      )}
    </section>
  );
}
