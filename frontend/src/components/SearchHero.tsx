import { MapContainer, TileLayer } from "react-leaflet";
import type { ActiveLocation, LocationSuggestion } from "../types";
import { LocationSearchInput } from "./LocationSearchInput";

const DEFAULT_CENTER: [number, number] = [42.38, -71.115]; // Cambridge/Somerville, MA — where the demo data lives

interface SearchHeroProps {
  query: string;
  onQueryChange: (value: string) => void;
  suggestions: LocationSuggestion[];
  onSelect: (location: ActiveLocation) => void;
  onSubmit: (text: string) => void;
}

export function SearchHero({ query, onQueryChange, suggestions, onSelect, onSubmit }: SearchHeroProps) {
  return (
    <div className="search-hero">
      <MapContainer
        center={DEFAULT_CENTER}
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
          Any real place — a neighborhood, a specific Starbucks, an address. Harvard Square and Davis Square have
          the richest demo data, but search finds real businesses everywhere.
        </p>
        <LocationSearchInput
          value={query}
          onChange={onQueryChange}
          suggestions={suggestions}
          onSelect={onSelect}
          onSubmit={onSubmit}
          placeholder="Try “Starbucks, Cambridge MA”…"
          autoFocus
        />
      </div>
    </div>
  );
}
