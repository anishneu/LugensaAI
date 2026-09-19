import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { useEffect } from "react";
import { MapContainer, Marker, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
import type { ActiveLocation } from "../types";

const defaultIcon = L.icon({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
  iconSize: [30, 46],
  iconAnchor: [15, 46],
});

interface WorkspaceHeaderProps {
  location: ActiveLocation;
  onChangeLocation: () => void;
}

/** react-leaflet only reads `center`/`zoom` when the map first mounts, so a
 * location whose coordinates arrive later (typed text, geocoded afterwards)
 * would leave the map stranded wherever it started. */
function Recenter({ lat, lng, zoom }: { lat: number; lng: number; zoom: number }) {
  const map = useMap();
  useEffect(() => {
    map.setView([lat, lng], zoom);
  }, [map, lat, lng, zoom]);
  return null;
}

export function WorkspaceHeader({ location, onChangeLocation }: WorkspaceHeaderProps) {
  const navigate = useNavigate();
  const hasCoords = location.latitude != null && location.longitude != null;
  const position: [number, number] | null = hasCoords ? [location.latitude!, location.longitude!] : null;

  return (
    <header className="relative h-56 w-full flex-shrink-0 overflow-hidden border-b border-[var(--border)] bg-[var(--bg-alt)] sm:h-64">
      <div className="absolute inset-0">
        {position ? (
          <MapContainer
            center={position}
            zoom={15}
            zoomControl={false}
            dragging={false}
            scrollWheelZoom={false}
            doubleClickZoom={false}
            attributionControl={false}
            className="h-full w-full grayscale-[35%]"
          >
            <Recenter lat={position[0]} lng={position[1]} zoom={15} />
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            <Marker position={position} icon={defaultIcon} />
          </MapContainer>
        ) : (
          // No coordinates yet: show nothing rather than a map of somewhere
          // else — a wrong pin is worse than no pin.
          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-violet-950 to-slate-900 text-sm text-white/60">
            Locating on the map…
          </div>
        )}
      </div>

      {/* Legibility gradient so the overlaid text/controls read cleanly over
          arbitrary map tiles regardless of theme. */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/75 via-black/10 to-black/40" />

      <div className="relative z-10 flex h-full flex-col justify-between p-4 sm:p-5">
        <div className="flex items-start justify-between">
          <button
            className="rounded-full border border-white/20 bg-black/30 px-3.5 py-1.5 text-sm font-extrabold text-white backdrop-blur-sm transition hover:border-white/40"
            onClick={() => navigate("/")}
            type="button"
            title="Back to landing page"
          >
            Lugensa<span className="text-violet-300">AI</span>
          </button>

          <button
            type="button"
            className="flex-shrink-0 rounded-full border border-white/25 bg-black/30 px-4 py-1.5 text-[13px] font-medium text-white backdrop-blur-sm transition hover:border-white/50"
            onClick={onChangeLocation}
          >
            Change location
          </button>
        </div>

        <motion.div
          className="flex flex-col gap-1"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: "easeOut" }}
        >
          <span className="text-xs font-semibold uppercase tracking-[0.08em] text-white/70">📍 Researching</span>
          <h1 className="m-0 max-w-[80ch] truncate text-2xl font-extrabold text-white drop-shadow-sm sm:text-3xl">
            {location.displayName}
          </h1>
        </motion.div>
      </div>
    </header>
  );
}
