import L from "leaflet";

/** The tile layers every map in the app is built from — one place so the
 * replay map (components/race/MapView) and the standalone explorer map
 * (components/map/ExplorerMap) can't drift apart on tile source, zoom limits
 * or attribution.
 *
 * `seamark` is OpenSeaMap's nautical overlay: a transparent raster layer of
 * buoys, lights, harbours and depth marks, meant to be drawn *on top of* the
 * OSM base rather than replacing it. Both are third-party hosts contacted
 * directly by the browser — see the "third-party map services" section of the
 * privacy policy (frontend/src/content/legal/privacy.ts). */
export function createBaseLayers(): { base: L.TileLayer; seamark: L.TileLayer } {
  return {
    base: L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
      maxZoom: 19,
    }),
    seamark: L.tileLayer("https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png", {
      attribution: "© OpenSeaMap contributors",
      // OpenSeaMap has no seamark tiles past z18; letting Leaflet ask for
      // z19 would just blank the overlay when the base is still fine.
      maxZoom: 18,
      maxNativeZoom: 18,
    }),
  };
}
