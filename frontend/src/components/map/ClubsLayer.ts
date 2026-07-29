import L from "leaflet";
import { escapeHtml } from "@/utils/html";
import type { Club } from "@/types";
import styles from "./ClubMarkers.module.css";

/** Clubs that have coordinates set, as round logo (or initial) markers. Same
 * imperative shape as syncPoiLayer — see PoiLayer.ts.
 *
 * `onOpen` gets the club id when the popup's link is clicked; the caller
 * routes with react-router rather than letting a plain `<a href>` trigger a
 * full page reload out of the SPA. */
export function syncClubsLayer(
  group: L.LayerGroup,
  clubs: Club[],
  labels: { open: string },
  onOpen: (clubId: string) => void,
): void {
  group.clearLayers();
  for (const club of clubs) {
    if (club.lat == null || club.lng == null) continue;
    const inner = club.logo
      ? `<img src="${encodeURI(club.logo.url)}" alt="">`
      : `<span>${escapeHtml(club.name.trim().slice(0, 1).toUpperCase())}</span>`;
    const marker = L.marker([club.lat, club.lng], {
      icon: L.divIcon({
        className: styles.pin,
        html: `<span class="${styles.badge}">${inner}</span><span class="${styles.tail}"></span>`,
        iconSize: [30, 38],
        iconAnchor: [15, 38],
      }),
    });
    marker.bindPopup(
      `<strong>${escapeHtml(club.name)}</strong>` +
        (club.city ? `<span class="${styles.popupCity}">${escapeHtml(club.city)}</span>` : "") +
        `<button type="button" class="${styles.popupLink}">${escapeHtml(labels.open)}</button>`,
      { className: styles.popup },
    );
    marker.on("popupopen", (e: L.PopupEvent) => {
      e.popup
        .getElement()
        ?.querySelector<HTMLButtonElement>(`.${styles.popupLink}`)
        ?.addEventListener("click", () => onOpen(club.id));
    });
    group.addLayer(marker);
  }
}
