import L from "leaflet";
import { escapeHtml } from "@/utils/html";
import type { Club } from "@/types";
import { bindExpandableMarker, collapseExpandable } from "./expandableMarker";
import styles from "./ClubMarkers.module.css";

/** Clubs that have coordinates set, as round logo (or initial) markers. Same
 * imperative shape as syncPoiLayer — see PoiLayer.ts.
 *
 * Tapping a pin expands it in place into a card with the logo, name, city and
 * an "open the club" action (see expandableMarker), rather than opening a
 * Leaflet popup — the card is part of the pin, so it stays anchored to the
 * club's position and is styled like the rest of the app.
 *
 * `onOpen` gets the club id when the card's action is used; the caller routes
 * with react-router rather than letting a plain `<a href>` trigger a full page
 * reload out of the SPA. */
export function syncClubsLayer(
  map: L.Map,
  group: L.LayerGroup,
  clubs: Club[],
  labels: { open: string },
  onOpen: (clubId: string) => void,
): void {
  group.clearLayers();
  for (const club of clubs) {
    if (club.lat == null || club.lng == null) continue;
    const initial = club.name.trim().slice(0, 1).toUpperCase();
    // escapeHtml, NOT encodeURI: the URL is already a finished one (a
    // presigned S3/MinIO link, see backend/services/media.py), and encodeURI
    // would re-escape its `%` sequences — `%2F` becoming `%252F` breaks the
    // signature and the logo 403s. This only needs the attribute made safe.
    const logo = club.logo
      ? `<img src="${escapeHtml(club.logo.url)}" alt="">`
      : escapeHtml(initial);

    const marker = L.marker([club.lat, club.lng], {
      icon: L.divIcon({
        className: styles.pin,
        html:
          `<span class="${styles.inner}">` +
          `<span class="${styles.badge}">${logo}</span>` +
          `<span class="${styles.card}">` +
          `<span class="${styles.cardHead}">` +
          `<span class="${styles.cardLogo}">${logo}</span>` +
          `<span class="${styles.cardText}">` +
          `<strong class="${styles.cardName}">${escapeHtml(club.name)}</strong>` +
          (club.city ? `<span class="${styles.cardCity}">${escapeHtml(club.city)}</span>` : "") +
          `</span></span>` +
          `<button type="button" class="${styles.cardOpen}">${escapeHtml(labels.open)}</button>` +
          `</span>` +
          `<span class="${styles.tail}"></span>` +
          `</span>`,
        // Zero-size anchor + the wrapper's own translate (see the CSS): the
        // expanded card is wider than the badge, and this keeps the tail's tip
        // on the club's exact coordinates in both states.
        iconSize: [0, 0],
        iconAnchor: [0, 0],
      }),
    });

    marker.on("add", () => {
      const el = marker.getElement();
      if (!el) return;
      el.querySelector<HTMLButtonElement>(`.${styles.cardOpen}`)?.addEventListener("click", (e) => {
        // Otherwise the click bubbles to the icon and Leaflet reads it as a
        // tap on the pin, collapsing the card the user just acted on.
        e.stopPropagation();
        onOpen(club.id);
      });
      // A logo whose object was deleted (or whose presigned link expired)
      // would leave an empty circle — fall back to the same initial a club
      // without a logo gets. textContent, so the name can't inject markup.
      el.querySelectorAll("img").forEach((img) => {
        img.addEventListener("error", () => {
          if (img.parentElement) img.parentElement.textContent = initial;
        });
      });
    });
    bindExpandableMarker(marker, map, styles.inner, styles.expanded);
    group.addLayer(marker);
  }
}

/** Collapses any open club card — bound to the map's own click by the caller,
 * so tapping the water closes the card. */
export function collapseClubCards(map: L.Map): void {
  collapseExpandable(map, styles.inner, styles.expanded);
}
