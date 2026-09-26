/** Google News' own search for a place over the last 30 days: the full results, which the live feed's headline-only list cannot show.
 * The name is quoted so a street is matched as a phrase, and the city is added so a shared name means this one. */
export function googleNewsSearchUrl(place: { displayName: string; city: string | null }): string {
  const name = place.displayName.split(",")[0].trim();
  const query = `"${name}" ${place.city ?? ""} when:30d`.replace(/\s+/g, " ").trim();
  return `https://news.google.com/search?q=${encodeURIComponent(query)}&hl=en-US&gl=US&ceid=US:en`;
}

/** Where "open in a new window" goes: Google Maps at exact coordinates. No API key involved. */
export function googleMapsUrl(latitude: number, longitude: number): string {
  return `https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`;
}

// Six decimals is about ten centimetres; more only makes a long URL (a float can print as 50.972758500000005).
const coord = (value: number) => Number(value.toFixed(6));

// Stops and entrances are mapped as points, not as businesses: Google has no listing named like OpenStreetMap's
// ("Manchester City Centre, Princess Street / Art Gallery (Stop SD)" matched the gallery and another stop when
// tried), so a search by name lands on the wrong thing. Their exact coordinates are the accurate link.
const POINT_KINDS = new Set(["bus stop", "tram stop", "subway entrance"]);

/**
 * A link for one place from the map data. Coordinates alone open a bare pin titled with the numbers, not the place; a
 * search for the place's name (and street, when the map has it) centered on its coordinates opens the actual listing,
 * and picks the branch on that spot when the name is a chain's. Falls back to the exact-coordinate pin for stops.
 */
export function placeMapsUrl(place: { name: string; kind: string; address?: string | null; latitude: number; longitude: number }): string {
  if (POINT_KINDS.has(place.kind)) return googleMapsUrl(place.latitude, place.longitude);
  const search = encodeURIComponent([place.name, place.address].filter(Boolean).join(" "));
  return `https://www.google.com/maps/search/${search}/@${coord(place.latitude)},${coord(place.longitude)},19z`;
}

/**
 * The link for the researched pin itself (the map panel's button, and a click on its map). Coordinates alone open a bare
 * pin titled with the numbers, which looks like a different spot from the place's own listing even when it is the same
 * point (checked on a hotel: the coordinate pin and the listing's marker were the same spot, and it still looked wrong). So a
 * place opens as a search for its name, or for its address, centered on the pin's coordinates: the real listing, at the
 * right spot. A pin without coordinates has no link.
 */
export function pinMapsUrl(pin: {
  displayName: string;
  city: string | null;
  isBusiness: boolean;
  isAddress: boolean;
  googlePlaceId?: string | null;
  latitude: number;
  longitude: number;
}): string {
  const name = pin.displayName.split(",")[0].trim();
  // An address is searched as written; anything else by its name and city, which tells a chain's branches apart.
  const text = pin.isAddress ? pin.displayName : [name, pin.city && !name.includes(pin.city) ? pin.city : ""].filter(Boolean).join(" ");
  // A pin picked from a Google result carries Google's own id, which opens exactly that listing (a search for a hotel's
  // name opens Google's hotel results, with ads, instead).
  if (pin.googlePlaceId && text) return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(text)}&query_place_id=${encodeURIComponent(pin.googlePlaceId)}`;
  if (!text) return googleMapsUrl(pin.latitude, pin.longitude);
  // A single place is shown close in; an area or a street is left at a wider view.
  const zoom = pin.isBusiness || pin.isAddress ? 19 : 16;
  return `https://www.google.com/maps/search/${encodeURIComponent(text)}/@${coord(pin.latitude)},${coord(pin.longitude)},${zoom}z`;
}
