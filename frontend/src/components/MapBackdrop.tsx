import searchMap from "../assets/search-map.webp";

/**
 * The search page's backdrop: a still street map of Midtown Manhattan (OpenStreetMap data, drawn once from OpenFreeMap's tiles)
 * that drifts slowly along a diagonal. It is an image and not a live map on purpose: a live map waited on tile requests and
 * WebGL and showed up seconds after the rest of the page, whereas an image is there with it. The page's credit for the map data
 * is in `SearchHero`. The drift is a CSS animation (see `.map-drift` in index.css), switched off for anyone who has asked for
 * reduced motion, and it never shows the image's edges because the image is larger than the page by more than it travels.
 */
export default function MapBackdrop() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden bg-[#0b0a14]" aria-hidden="true">
      <img
        src={searchMap}
        alt=""
        width={2560}
        height={1600}
        fetchPriority="high"
        decoding="async"
        className="map-drift absolute -inset-[6%] h-[112%] w-[112%] max-w-none object-cover"
      />
    </div>
  );
}
