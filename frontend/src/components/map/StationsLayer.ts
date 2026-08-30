import L from "leaflet";
import { escapeHtml } from "@/utils/html";
import type { WindStation } from "@/types";
import { bindExpandableMarker, collapseExpandable } from "./expandableMarker";
import styles from "./StationMarkers.module.css";

/** The real weather stations feeding the wind estimate, as pins. Same
 * imperative shape as syncClubsLayer/syncPoiLayer.
 *
 * This layer is what makes the data sources visible to a sailor: which
 * stations exist near where they sail, and whether one is actually alive.
 * The Open-Meteo models deliberately have no pin — they are queried at any
 * coordinate and have no position to draw — so they are listed on the info
 * page instead, not faked onto the map as a marker somewhere.
 *
 * A station without coordinates is skipped, exactly as the backend's
 * `find_within` skips it. */
export function syncStationsLayer(
  map: L.Map,
  group: L.LayerGroup,
  stations: WindStation[],
  labels: { noReading: string; ago: (minutes: number) => string },
): void {
  group.clearLayers();
  for (const station of stations) {
    if (station.lat == null || station.lng == null) continue;
    const name = station.name ?? station.external_station_id;
    const last = station.last_observation ?? null;

    const reading =
      last && (last.tws_kts != null || last.twd_deg != null)
        ? `<span class="${styles.reading}">` +
          `<span class="${styles.readingValue}">` +
          (last.tws_kts != null ? `${escapeHtml(String(last.tws_kts))} kn` : "—") +
          `</span><span>` +
          (last.twd_deg != null ? `${escapeHtml(String(Math.round(last.twd_deg)))}°` : "") +
          `</span></span>` +
          `<span class="${styles.cardMeta}">` +
          escapeHtml(labels.ago(minutesSince(last.observed_at))) +
          `</span>`
        : `<span class="${styles.cardMeta}">${escapeHtml(labels.noReading)}</span>`;

    const marker = L.marker([station.lat, station.lng], {
      icon: L.divIcon({
        className: styles.pin,
        html:
          `<span class="${styles.inner}">` +
          // The badge glyph is inline text, not an icon font: this markup is
          // built as a string for Leaflet's divIcon, outside React.
          `<span class="${styles.badge}">🜁</span>` +
          `<span class="${styles.card}">` +
          `<strong class="${styles.cardName}">${escapeHtml(name)}</strong>` +
          `<span class="${styles.cardMeta}">${escapeHtml(station.provider)}</span>` +
          reading +
          `</span>` +
          `<span class="${styles.tail}"></span>` +
          `</span>`,
        // Zero-size anchor + the wrapper's own translate (see the CSS), so the
        // tail's tip stays on the station's coordinates in both states.
        iconSize: [0, 0],
        iconAnchor: [0, 0],
      }),
    });

    bindExpandableMarker(marker, map, styles.inner, styles.expanded);
    group.addLayer(marker);
  }
}

function minutesSince(iso: string): number {
  return Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
}

/** Collapses any open station card — bound to the map's own click by the
 * caller, so tapping the water closes the card. */
export function collapseStationCards(map: L.Map): void {
  collapseExpandable(map, styles.inner, styles.expanded);
}
