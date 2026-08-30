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
      // Don't fetch the intermediate tiles a zoom animation passes through.
      updateWhenZooming: false,
      // Leaflet's default (2) keeps two rings of off-screen tiles loaded; one is enough.
      keepBuffer: 1,
    }),
    seamark: L.tileLayer("https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png", {
      attribution: "© OpenSeaMap contributors",
      // OpenSeaMap has no seamark tiles past z18; letting Leaflet ask for
      // z19 would just blank the overlay when the base is still fine.
      maxZoom: 18,
      maxNativeZoom: 18,
      // Measured against tiles.openseamap.org over the Adriatic: z4/z6/z8 all
      // came back as the same 334 B blank PNG, z9 was the first with content
      // (704 B) — below z9 the overlay draws nothing, so don't request it.
      minZoom: 9,
      // Don't fetch the intermediate tiles a zoom animation passes through.
      updateWhenZooming: false,
      // Leaflet's default (2) keeps two rings of off-screen tiles loaded; one is enough.
      keepBuffer: 1,
    }),
  };
}
