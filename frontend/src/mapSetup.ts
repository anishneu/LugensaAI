import { setWorkerUrl } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

// MapLibre finds its worker with `new URL("./maplibre-gl-worker.mjs", import.meta.url)`, which points at a file that
// does not exist once Vite has bundled the library (the map style loads but no tile is ever parsed, so the map stays
// blank). Handing it a Vite-built worker URL explicitly fixes both `npm run dev` and `npm run build`.
setWorkerUrl(workerUrl);

// OpenFreeMap: free vector tiles from OpenStreetMap data, no API key or account. Its style prints a place's English
// (Latin-script) name first and the local script beneath it, so a street in Tokyo reads "Meiji-dori" with 明治通り
// under it: English primary, the local language secondary. (OpenStreetMap's own tiles show only the local script,
// and CARTO's free tiles now require a key.) The light style is used in dark mode too: a map is a reference to be
// read, and the dark one rendered as near-black with unreadable labels.
export const MAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";
