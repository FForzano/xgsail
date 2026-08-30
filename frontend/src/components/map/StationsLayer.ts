import L from "leaflet";
import { escapeHtml } from "@/utils/html";
import type { WindStation } from "@/types";
import { bindExpandableMarker } from "./expandableMarker";
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

    // Order: arrow, then the angle, then the speed — the glyph is what the eye
    // lands on first, and the number that qualifies it belongs next to it.
    const reading =
      last && (last.tws_kts != null || last.twd_deg != null)
        ? `<span class="${styles.reading}">` +
          (last.twd_deg != null ? directionMarkup(last.twd_deg) : "") +
          `<span class="${styles.readingValue}">` +
          (last.tws_kts != null ? `${escapeHtml(String(last.tws_kts))} kn` : "—") +
          `</span>` +
          `</span>` +
          `<span class="${styles.cardMeta}">` +
          escapeHtml(labels.ago(minutesSince(last.observed_at))) +
          `</span>`
        : `<span class="${styles.cardMeta}">${escapeHtml(labels.noReading)}</span>`;

    const marker = L.marker([station.lat, station.lng], {
      icon: L.divIcon({
        className: styles.pin,
        html:
          `<span class="${styles.inner}">` +
          `<span class="${styles.badge}">${WIND_GLYPH}</span>` +
          `<span class="${styles.card}">` +
          `<strong class="${styles.cardName}">${escapeHtml(name)}</strong>` +
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

// Lucide's "wind" glyph for the collapsed badge. Inline SVG rather than a text
// character: a glyph's own metrics decide where it sits in its line box, so it
// never lands dead centre of the circle, while an SVG box is centred by the
// badge's own flex rules.
const WIND_GLYPH =
  `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" ` +
  `stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">` +
  `<path d="M12.8 19.6A2 2 0 1 0 14 16H2M17.5 4.5A2 2 0 1 1 19 8H2M9.8 4.4A2 2 0 1 1 11 8H2"/></svg>`;

// Arrow-up glyph (the lucide icon WindBadge renders as a component), inlined
// as a path because this markup is a string for Leaflet's divIcon.
const ARROW_UP =
  `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" ` +
  `stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">` +
  `<path d="M12 19V5M5 12l7-7 7 7"/></svg>`;

/** Wind direction as an arrow plus the number: a sailor reads the glyph
 * instantly where `245°` takes a moment.
 *
 * `twd_deg` is the direction the wind blows FROM, in degrees clockwise from
 * north — the pipeline's convention throughout (see `to_uv` in
 * libs/xgsail_windfusion). The arrow points where the wind is blowing TOWARD,
 * so it reads as flow rather than as a bearing back to its source: hence the
 * +180, matching WindBadge. */
function directionMarkup(twdDeg: number): string {
  const rotation = (twdDeg + 180) % 360;
  return (
    `<span class="${styles.direction}">` +
    `<span class="${styles.directionArrow}" style="transform: rotate(${escapeHtml(String(rotation))}deg)">` +
    ARROW_UP +
    `</span>` +
    `${escapeHtml(String(Math.round(twdDeg)))}°` +
    `</span>`
  );
}

function minutesSince(iso: string): number {
  return Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
}
