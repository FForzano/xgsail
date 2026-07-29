import L from "leaflet";
import { escapeHtml } from "@/utils/html";
import type { NauticalPoi } from "@/services/overpass";
import { poiIcon } from "./poiIcons";
import styles from "./PoiMarkers.module.css";

/** Redraws `group` to hold exactly one pin per POI. Imperative (not a React
 * component) to match how every other Leaflet layer in the app is managed —
 * see MapView's marks layer. */
export function syncPoiLayer(
  group: L.LayerGroup,
  pois: NauticalPoi[],
  kindLabel: (poi: NauticalPoi) => string,
): void {
  group.clearLayers();
  for (const poi of pois) {
    const marker = L.marker([poi.lat, poi.lng], { icon: poiIcon(poi.kind) });
    const osmUrl = `https://www.openstreetmap.org/${poi.osmType}/${poi.osmId}`;
    marker.bindPopup(
      `<strong>${escapeHtml(poi.name ?? kindLabel(poi))}</strong>` +
        `<span class="${styles.popupKind}">${escapeHtml(kindLabel(poi))}</span>` +
        `<a href="${osmUrl}" target="_blank" rel="noreferrer">OpenStreetMap</a>`,
      { className: styles.popup },
    );
    group.addLayer(marker);
  }
}
