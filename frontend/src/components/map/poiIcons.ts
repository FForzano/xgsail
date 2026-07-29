import L from "leaflet";
import type { PoiKind } from "@/services/overpass";
import styles from "./PoiMarkers.module.css";

// Simplified lucide-react glyphs, inlined as raw paths: these go into a
// Leaflet divIcon's `html` string, which can't render a React component.
const GLYPHS: Record<PoiKind, string> = {
  marina: "M22 18H2a4 4 0 0 0 4 4h12a4 4 0 0 0 4-4M21 14 10 2v12M3 14h18",
  sailing_club: "M22 18H2a4 4 0 0 0 4 4h12a4 4 0 0 0 4-4M21 14 10 2v12M3 14h18",
  harbour: "M12 22V8M12 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6M5 12H2a10 10 0 0 0 20 0h-3",
  anchorage: "M12 22V8M12 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6M5 12H2a10 10 0 0 0 20 0h-3",
  slipway: "M3 20h18M6 20 16 9h4",
  fuel: "M3 22h12M4 9h10M14 22V4a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v18M14 13h2a2 2 0 0 1 2 2v2a2 2 0 0 0 4 0V9.8a2 2 0 0 0-.6-1.4L18 5",
  sports_area: "M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1zM4 22v-7",
};

const KIND_CLASS: Record<PoiKind, string> = {
  marina: styles.kindMarina,
  harbour: styles.kindHarbour,
  anchorage: styles.kindAnchorage,
  slipway: styles.kindSlipway,
  sailing_club: styles.kindSailingClub,
  sports_area: styles.kindSportsArea,
  fuel: styles.kindFuel,
};

/** Pin for a nautical POI: same circle+tail geometry (and 26×33 box, anchored
 * at the bottom tip) as MapView's maneuver pins, so nautical POIs and race
 * marks read as one visual family. */
export function poiIcon(kind: PoiKind): L.DivIcon {
  return L.divIcon({
    className: `${styles.pin} ${KIND_CLASS[kind]}`,
    html:
      `<span class="${styles.circle}">` +
      `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" ` +
      `stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">` +
      `<path d="${GLYPHS[kind]}"/></svg>` +
      `</span>` +
      `<span class="${styles.tail}"></span>`,
    iconSize: [26, 33],
    iconAnchor: [13, 33],
  });
}
