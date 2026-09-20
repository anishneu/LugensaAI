import { useState } from "react";
import { MapContainer, TileLayer } from "react-leaflet";
import type { ActiveLocation } from "../types";
import { LocationSearchInput } from "./LocationSearchInput";

// A decorative street-map backdrop, a different world city each visit. It carries no data and implies
// no particular place: the app is not about any one city.
const BACKDROP_CITIES: [number, number][] = [
  [35.6595, 139.7005], // Tokyo
  [48.8534, 2.3488], // Paris
  [30.0444, 31.2357], // Cairo
  [-1.2921, 36.8219], // Nairobi
  [-23.5505, -46.6333], // Sao Paulo
  [-33.8688, 151.2093], // Sydney
  [41.0082, 28.9784], // Istanbul
  [19.076, 72.8777], // Mumbai
  [52.52, 13.405], // Berlin
];

interface SearchHeroProps {
  query: string;
  onQueryChange: (value: string) => void;
  onSelect: (location: ActiveLocation) => void;
  onSubmit: (text: string) => void;
}

export function SearchHero({ query, onQueryChange, onSelect, onSubmit }: SearchHeroProps) {
  const [backdrop] = useState(() => BACKDROP_CITIES[Math.floor(Math.random() * BACKDROP_CITIES.length)]);
  return (
    <div className="search-hero">
      <MapContainer
        center={backdrop}
        zoom={13}
        zoomControl={false}
        scrollWheelZoom={false}
        dragging={false}
        doubleClickZoom={false}
        className="search-hero-map"
      >
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      </MapContainer>
      <div className="search-hero-overlay" />

      <div className="search-hero-content">
        <h1>Where should the agent investigate?</h1>
        <p>
          Any real place, anywhere in the world: a neighborhood, a specific restaurant, an address, or a Google
          Maps plus code.
        </p>
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
  );
}
