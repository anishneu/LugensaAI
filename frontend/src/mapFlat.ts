/** The pieces of a MapLibre map that `flattenMap` uses, so it can be tested without a map. */
interface FlattenableMap {
  getStyle(): { layers?: { id: string; type: string }[] };
  removeLayer(id: string): unknown;
}

/**
 * Makes a map two-dimensional: removes the style's extruded (3D) building layers. OpenFreeMap's "liberty" style draws buildings as
 * raised shapes from about zoom 14, and at the zoom the pin map uses their dark sides make a city centre look tilted and busy. The flat
 * building outlines underneath stay, and so do streets, names and stops. Returns how many layers it removed.
 */
export function flattenMap(map: FlattenableMap): number {
  const extruded = (map.getStyle().layers ?? []).filter((layer) => layer.type === "fill-extrusion");
  for (const layer of extruded) map.removeLayer(layer.id);
  return extruded.length;
}
