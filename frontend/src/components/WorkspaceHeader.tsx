import { useNavigate } from "react-router-dom";
import { MapContainer, Marker, TileLayer } from "react-leaflet";
import L from "leaflet";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
import type { ActiveLocation } from "../types";

const defaultIcon = L.icon({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
  iconSize: [20, 33],
  iconAnchor: [10, 33],
});

interface WorkspaceHeaderProps {
  location: ActiveLocation;
  onChangeLocation: () => void;
}

export function WorkspaceHeader({ location, onChangeLocation }: WorkspaceHeaderProps) {
  const navigate = useNavigate();
  const hasCoords = location.latitude != null && location.longitude != null;
  const position: [number, number] = hasCoords ? [location.latitude!, location.longitude!] : [42.38, -71.115];

  return (
    <header className="workspace-header">
      <button className="brand-mini" onClick={() => navigate("/")} type="button" title="Back to landing page">
        Lugensa<span>AI</span>
      </button>

      <div className="header-map">
        <MapContainer
          center={position}
          zoom={hasCoords ? 14 : 11}
          zoomControl={false}
          dragging={false}
          scrollWheelZoom={false}
          doubleClickZoom={false}
          attributionControl={false}
          className="header-map-inner"
        >
          <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          {hasCoords && <Marker position={position} icon={defaultIcon} />}
        </MapContainer>
      </div>

      <div className="header-location-text">
        <span className="header-location-label">Researching</span>
        <span className="header-location-name">{location.displayName}</span>
      </div>

      <button type="button" className="change-location-button" onClick={onChangeLocation}>
        Change location
      </button>
    </header>
  );
}
