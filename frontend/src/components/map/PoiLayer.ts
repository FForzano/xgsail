import L from "leaflet";
import { escapeHtml } from "@/utils/html";
import type { NauticalPoi } from "@/services/overpass";
import { poiIcon } from "./poiIcons";
import styles from "./PoiMarkers.module.css";

/** Redraws `group` to hold exactly one pin per POI. Imperative (not a React
 * component) to match how every other Leaflet layer in the app is managed —
 * see MapView's marks layer.
 *
 * `onCreateClub` is called with a sailing-club POI when its popup's "create
 * club" action is used; the caller routes with react-router rather than
 * letting a plain `<a href>` trigger a full page reload out of the SPA —
 * same reasoning as syncClubsLayer's `onOpen`. The button only exists once
 * the popup is open, so the handler binds on the marker's `popupopen` event
 * rather than `add` (see syncClubsLayer, which binds on `add` because its
 * card is always in the DOM). */
export function syncPoiLayer(
  group: L.LayerGroup,
  pois: NauticalPoi[],
  kindLabel: (poi: NauticalPoi) => string,
  createClubLabel: string,
  onCreateClub: (poi: NauticalPoi) => void,
): void {
  group.clearLayers();
  for (const poi of pois) {
    const marker = L.marker([poi.lat, poi.lng], { icon: poiIcon(poi.kind) });
    const osmUrl = `https://www.openstreetmap.org/${poi.osmType}/${poi.osmId}`;
    const createClubButton =
      poi.kind === "sailing_club"
        ? `<button type="button" class="${styles.popupCreateClub}">${escapeHtml(createClubLabel)}</button>`
        : "";
    marker.bindPopup(
      `<strong>${escapeHtml(poi.name ?? kindLabel(poi))}</strong>` +
        `<span class="${styles.popupKind}">${escapeHtml(kindLabel(poi))}</span>` +
        `<a href="${osmUrl}" target="_blank" rel="noreferrer">OpenStreetMap</a>` +
        createClubButton,
      { className: styles.popup },
    );
    if (poi.kind === "sailing_club") {
      marker.on("popupopen", () => {
        const btn = marker
          .getPopup()
          ?.getElement()
          ?.querySelector<HTMLButtonElement>(`.${styles.popupCreateClub}`);
        // popupopen fires on every open, and Leaflet reuses the popup's
        // container across them — the guard keeps a reopened popup from
        // stacking a second handler and firing two navigations.
        if (!btn || btn.dataset.bound) return;
        btn.dataset.bound = "1";
        btn.addEventListener("click", () => onCreateClub(poi));
      });
    }
    group.addLayer(marker);
  }
}
