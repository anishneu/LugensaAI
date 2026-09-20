/** Where "open in a new window" goes: Google Maps at exact coordinates. No API key involved. */
export function googleMapsUrl(latitude: number, longitude: number): string {
  return `https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`;
}
