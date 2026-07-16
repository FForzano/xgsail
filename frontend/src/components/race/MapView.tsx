import { useEffect, useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { timeController, useTimeState } from "@/stores/timeController";
import { useWindAt } from "@/hooks/useWindAt";
import { fmtKnots } from "@/utils/format";
import type { TrueWindPoint, VmgPoint } from "@/types";
import {
  catmullRomInterval,
  pointAt,
  smoothTrackLine,
  speedColor,
  speedRange,
  vmgAt,
  type Track,
  type TrackPoint,
} from "./raceModel";

// Track/boat names are user-supplied data (boat.name) inserted into popup
// innerHTML below — must be escaped, unlike the rest of popupContent which is
// only translated strings and formatted numbers.
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Nearest track point to a click/drag, by plain lat/lon distance (only used
// to pick "which fix", not a real distance — squared error is fine).
function nearestPoint(tr: Track, latlng: L.LatLng) {
  let best = tr.pts[0];
  let bestD = Infinity;
  for (const p of tr.pts) {
    const d = (p.lat - latlng.lat) ** 2 + (p.lon - latlng.lng) ** 2;
    if (d < bestD) {
      bestD = d;
      best = p;
    }
  }
  return best;
}

export interface MapMark {
  id?: string;
  mark_role: string;
  lat: number;
  lng: number;
  /** preview marks (suggest/auto-start-line before apply) render dashed */
  preview?: boolean;
  /** "leg" marks render as a numbered circle (see `seq`), colored by
   * `legType`; "maneuver" marks render as a colored pin (colored by
   * `maneuverType`) with `mark_role`'s first letter. "maneuver-pending" is a
   * manually-added maneuver awaiting the worker's stat computation (see
   * SessionDetailPage's maneuver-edit mode); "maneuver-draft" is the
   * in-progress start/end pick before it's even submitted (no type yet, so no
   * color). Omit for the default diamond (race marks: start/windward/gate/
   * finish…). */
  kind?: "leg" | "maneuver" | "maneuver-pending" | "maneuver-draft";
  /** Progressive number shown on "leg" marks (matches the LegsTable `#` column). */
  seq?: number;
  /** Which bordata this "leg" mark is — drives its color (see .sf-markicon--leg-*). */
  legType?: "upwind" | "downwind" | "reach";
  /** Which maneuver this "maneuver"/"maneuver-pending" mark is — drives its
   * color (see .sf-markicon--tack/--gybe/--course_change). */
  maneuverType?: "tack" | "gybe" | "course_change";
}

// Imperative Leaflet (not react-leaflet): tracks + marks are drawn once, and
// only the per-boat position markers move on every cursor tick — kept in refs
// so playback doesn't churn React's tree. No hardcoded geography: the view
// always fits the data; with no data it shows a neutral world view.
export function MapView({
  tracks,
  marks = [],
  className = "sf-race__map",
  wind,
  sessionWind,
  vmg,
  mapOptions,
  controls,
  placementMode = false,
  onManeuverPlacement,
  onOpenSession,
}: {
  tracks: Track[];
  marks?: MapMark[];
  className?: string;
  /** Region to show a wind direction/speed overlay for (e.g. the session's
   * start point + start time) — omit to hide the overlay entirely. Ignored
   * for the actual value shown whenever `sessionWind` has a usable point;
   * still used as the time to look up (`wind.at`) and as the live-snapshot
   * fallback when it doesn't. */
  wind?: { lat: number; lng: number; at?: string | null };
  /** This session's own determined true-wind series (`session_analysis.
   * true_wind`, see workers/process_upload/processing/wind_estimation.py)
   * — preferred over the live WindCard-style snapshot when present, since
   * it's what VMG/polar/legs were actually computed against. */
  sessionWind?: TrueWindPoint[] | null;
  /** VMG series (session-scoped) — if given, the click-track popup shows VMG
   * alongside speed/course. */
  vmg?: VmgPoint[] | null;
  /** Rendered as a floating ⚙-style overlay, top-left (e.g. legs/maneuvers
   * toggles) — omit to show nothing there. */
  mapOptions?: ReactNode;
  /** Rendered as a floating overlay, bottom-center (the playback transport). */
  controls?: ReactNode;
  /** When true, clicking the track calls `onManeuverPlacement` with the
   * nearest real fix instead of the normal seek+info-popup behavior — the
   * session detail page's maneuver-edit mode uses this to let a user place
   * a manual maneuver's start/end by clicking the track twice. */
  placementMode?: boolean;
  onManeuverPlacement?: (point: { lat: number; lon: number; timestamp: number }) => void;
  /** Click handler for the popup's "more info" button (shown whenever there's
   * more than one track, e.g. the activity map) — called with that track's
   * session id (`tr.id`, see buildTrack/buildTracks) so the caller can
   * navigate to `/diario/sessions/{id}`. */
  onOpenSession?: (sessionId: string) => void;
}) {
  const { t } = useTranslation();
  const elRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<Record<string, L.Marker>>({});
  const marksLayerRef = useRef<L.LayerGroup | null>(null);
  // Tracks currently being drag-scrubbed — the cursor-sync effect below
  // skips these so it doesn't fight Leaflet's own drag handler.
  const draggingRef = useRef<Set<string>>(new Set());
  const { cursor } = useTimeState();
  // Read from the recenter button's click handler (defined once at setup
  // time) without forcing a full map rebuild on every playback tick.
  const cursorRef = useRef(cursor);
  // Same reasoning: read from the track's click handler (also set up once)
  // without rebuilding the whole map every time edit mode toggles.
  const placementModeRef = useRef(placementMode);
  placementModeRef.current = placementMode;
  const onManeuverPlacementRef = useRef(onManeuverPlacement);
  onManeuverPlacementRef.current = onManeuverPlacement;
  const onOpenSessionRef = useRef(onOpenSession);
  onOpenSessionRef.current = onOpenSession;
  const { data: windAt } = useWindAt(wind?.lat, wind?.lng, wind?.at);
  // Prefer this session's own determined wind (closest-in-time point) over
  // the live snapshot — it's what the session's own VMG/polar/legs were
  // actually computed against, not just a nearby model/station guess.
  // When a true-wind series is available, track it against the live replay
  // cursor (so the arrow updates as playback advances) rather than a fixed
  // instant — the static `wind.at` fallback only applies to the live-
  // snapshot case, where there's no series to scrub through.
  const targetMs = sessionWind?.length
    ? cursor
    : wind?.at
    ? Date.parse(wind.at)
    : Date.now();
  const sessionWindPoint = (sessionWind ?? []).reduce<TrueWindPoint | null>((best, p) => {
    if (p.twd_deg == null) return best;
    if (!best) return p;
    return Math.abs(p.timestamp * 1000 - targetMs) < Math.abs(best.timestamp * 1000 - targetMs)
      ? p
      : best;
  }, null);
  const displayWind = sessionWindPoint
    ? { twd_deg: sessionWindPoint.twd_deg, tws_kts: sessionWindPoint.tws_kts }
    : windAt
    ? { twd_deg: windAt.twd_deg, tws_kts: windAt.tws_kts }
    : null;

  // One-time map + static layer setup (rebuilt when the data identity changes).
  useEffect(() => {
    if (!elRef.current) return;
    const map = L.map(elRef.current, { zoomControl: false, preferCanvas: true });
    L.control.zoom({ position: "bottomright" }).addTo(map);

    const RecenterControl = L.Control.extend({
      onAdd() {
        const btn = L.DomUtil.create("button", "sf-map__recenter leaflet-bar");
        btn.type = "button";
        btn.title = "Recenter";
        btn.innerHTML =
          '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">' +
          '<circle cx="8" cy="8" r="2.5" fill="currentColor"/>' +
          '<path d="M8 0v3.5M8 12.5V16M0 8h3.5M12.5 8H16" stroke="currentColor" stroke-width="1.5"/>' +
          "</svg>";
        L.DomEvent.disableClickPropagation(btn);
        btn.onclick = () => {
          const pts = tracks
            .map((tr) => pointAt(tr, cursorRef.current))
            .filter((p): p is TrackPoint => p != null);
          if (!pts.length) return;
          if (pts.length === 1) map.panTo([pts[0].lat, pts[0].lon]);
          else map.fitBounds(L.latLngBounds(pts.map((p) => [p.lat, p.lon] as [number, number])).pad(0.2));
        };
        return btn;
      },
    });
    new RecenterControl({ position: "bottomright" }).addTo(map);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
      maxZoom: 19,
    }).addTo(map);
    mapRef.current = map;

    // Delegated listener (not bound per-popup) so it survives popupContent's
    // innerHTML being replaced on every drag tick (see the "drag" handler
    // below, which calls setContent again on the same popup instance).
    const container = map.getContainer();
    const onContainerClick = (e: MouseEvent) => {
      const btn = (e.target as HTMLElement).closest<HTMLElement>(".sf-map-popup__info");
      const sessionId = btn?.dataset.sessionId;
      if (sessionId) onOpenSessionRef.current?.(sessionId);
    };
    container.addEventListener("click", onContainerClick);

    const bounds: L.LatLngExpression[] = [];
    for (const tr of tracks) {
      const latlngs = tr.pts.map((p) => [p.lat, p.lon] as [number, number]);
      if (!latlngs.length) continue;
      // The drawn line is lightly smoothed, then curved through a Catmull-Rom
      // interpolation per interval — bounds/markers stay on the raw fixes so
      // the true recorded track/position is never altered, only how the line
      // connecting it looks (still one color per original interval, just
      // drawn as a curve through it instead of a straight chord).
      const smoothed = smoothTrackLine(tr.pts);
      // Colored by speed (per-segment) rather than a single flat track color,
      // so a glance at the line shows where the boat was fast vs. slow.
      const [minSog, maxSog] = speedRange(tr);
      for (let i = 1; i < tr.pts.length; i++) {
        const avgSog = (tr.pts[i - 1].sog + tr.pts[i].sog) / 2;
        const color = speedColor(avgSog, minSog, maxSog);
        const p0 = smoothed[Math.max(0, i - 2)];
        const p1 = smoothed[i - 1];
        const p2 = smoothed[i];
        const p3 = smoothed[Math.min(smoothed.length - 1, i + 1)];
        const curve = catmullRomInterval(p0, p1, p2, p3);
        for (let k = 1; k < curve.length; k++) {
          L.polyline([curve[k - 1], curve[k]], { color, weight: 3, opacity: 0.85 }).addTo(map);
        }
      }
      // Speed/VMG/course at a point, instantaneous (nearest sample), not a
      // time series — shared by the click popup and the drag-scrub popup.
      // "Course" here is the true wind angle, not raw compass heading — kept
      // to 0-180° + tack side (like the polar chart) rather than a 0-360°
      // bearing, since TWA is signed (+ = starboard, - = port).
      // "Open in new"-style arrow (not a plain "i") — reads as "go to the
      // session's details/analysis", which is what onOpenSession actually does.
      const moreInfoIcon =
        `<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">` +
        `<path d="M6 3h7v7M13 3 6.5 9.5M4 5.5v6.5a1 1 0 0 0 1 1h6.5" fill="none" ` +
        `stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>` +
        `</svg>`;
      const popupContent = (p: TrackPoint) => {
        // Prefer this track's own VMG series (activity/race maps, one per
        // session) over the map-wide `vmg` prop (session maps, a single track).
        const vp = vmgAt(tr.vmg ?? vmg, p.ms);
        const course = vp
          ? `${Math.round(Math.abs(vp.twa_deg))}° ${t(vp.twa_deg >= 0 ? "race.starboard" : "race.port")}`
          : "—";
        // The boat's own photo (first of Boat.photos), when there is one —
        // large, on the left, spanning the full height of the 4 text lines
        // beside it (see .sf-map-popup__thumb/-body).
        const thumb = tr.boatImageUrl
          ? `<img class="sf-map-popup__thumb" src="${escapeHtml(tr.boatImageUrl)}" alt="" />`
          : "";
        // Boat name always shown (a single-track session map still benefits
        // from the "more info" shortcut below), not just on multi-track
        // activity/race maps — bolder/larger than the stat rows below it so
        // it reads as the popup's title, not just another line of data.
        const boatName = `<span class="sf-map-popup__name">${escapeHtml(tr.name)}</span>`;
        // Only rendered when the caller actually handles it — otherwise (e.g.
        // RacePage/RaceManagePanel, which don't pass onOpenSession) it would
        // be a decorative icon that does nothing when clicked.
        const moreInfo = onOpenSession
          ? `<button type="button" class="sf-map-popup__info" data-session-id="${tr.id}" title="${t(
              "sessions.openSession",
            )}">${moreInfoIcon}</button>`
          : "";
        // Four text lines (name+link, speed, VMG, course) stacked to the
        // right of the photo, which stretches to match their combined height.
        return (
          `<div class="sf-map-popup__body">` +
          thumb +
          `<div class="sf-map-popup__col">` +
          `<div class="sf-map-popup__row">${boatName}${moreInfo}</div>` +
          `<strong>${fmtKnots(p.sog)}</strong>` +
          `<span>${t("sessions.vmg")} ${vp ? fmtKnots(vp.vmg_kts) : "—"}</span>` +
          `<span>${t("race.course")} ${course}</span>` +
          `</div>` +
          `</div>`
        );
      };

      // Invisible wide hit-test line over the raw fixes — the drawn line is
      // too fragmented (many tiny curved segments) to bind clicks on
      // directly. Clicking anywhere near the track seeks playback to the
      // nearest fix and shows its info in a popup.
      L.polyline(latlngs, { color: "#000", weight: 16, opacity: 0 })
        .addTo(map)
        .on("click", (e: L.LeafletMouseEvent) => {
          const p = nearestPoint(tr, e.latlng);
          if (placementModeRef.current) {
            onManeuverPlacementRef.current?.({ lat: p.lat, lon: p.lon, timestamp: p.ms / 1000 });
            return;
          }
          timeController.seek(p.ms);
          L.popup({ closeButton: false, className: "sf-map-popup" })
            .setLatLng([p.lat, p.lon])
            .setContent(popupContent(p))
            .openOn(map);
        });

      bounds.push(...latlngs);
      const icon = L.divIcon({
        className: "sf-posmarker",
        html: `<span style="background:${tr.color}"></span>`,
        iconSize: [16, 16],
        iconAnchor: [8, 8],
      });
      const m = L.marker(latlngs[0], { icon, draggable: true });
      // Boat-name tooltip only makes sense with more than one track (Activity/
      // Race overlays) — a single-boat Session map would just repeat itself.
      if (tracks.length > 1) m.bindTooltip(tr.name);
      // Dragging is constrained to the track: on every drag tick, snap the
      // marker to the nearest real fix, seek playback there, and follow with
      // a popup that updates live (same content as the click popup).
      let dragPopup: L.Popup | null = null;
      m.on("dragstart", () => {
        draggingRef.current.add(tr.id);
        const p = nearestPoint(tr, m.getLatLng());
        dragPopup = L.popup({ closeButton: false, className: "sf-map-popup" })
          .setLatLng([p.lat, p.lon])
          .setContent(popupContent(p))
          .openOn(map);
      });
      m.on("drag", () => {
        const p = nearestPoint(tr, m.getLatLng());
        m.setLatLng([p.lat, p.lon]);
        timeController.seek(p.ms);
        dragPopup?.setLatLng([p.lat, p.lon]).setContent(popupContent(p));
      });
      m.on("dragend", () => draggingRef.current.delete(tr.id));
      m.addTo(map);
      markersRef.current[tr.id] = m;
    }

    // Marks are drawn by their own effect (below) so toggling them — e.g. the
    // legs/maneuvers checkboxes — doesn't tear down and rebuild the whole map
    // (tiles, pan/zoom, tracks). Just fold their positions into the initial fit.
    for (const mk of marks) bounds.push([mk.lat, mk.lng]);

    if (bounds.length) map.fitBounds(L.latLngBounds(bounds).pad(0.1));
    else map.setView([20, 0], 2); // neutral world view when there is no data

    return () => {
      container.removeEventListener("click", onContainerClick);
      map.remove();
      mapRef.current = null;
      markersRef.current = {};
      marksLayerRef.current = null;
      draggingRef.current.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `marks` intentionally
    // excluded: only used above for the one-time initial bounds fit.
  }, [tracks, vmg, t, !!onOpenSession]);

  // Marks (legs/maneuvers/race marks) on their own layer group, redrawn
  // whenever they change without touching the map/tiles/tracks above.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const layer = L.layerGroup().addTo(map);
    for (const mk of marks) {
      let icon: L.DivIcon;
      if (mk.kind === "leg") {
        // Colored by point-of-sail (bordata) — see .sf-markicon--leg-* below;
        // falls back to the base rule's color if legType is somehow absent.
        const typeClass = mk.legType ? ` sf-markicon--leg-${mk.legType}` : "";
        icon = L.divIcon({
          className: `sf-markicon sf-markicon--leg${typeClass}`,
          html: `${mk.seq ?? ""}`,
          iconSize: [18, 18],
        });
      } else if (mk.kind === "maneuver" || mk.kind === "maneuver-pending") {
        // A colored pin (circle + pointing tail) instead of a plain dot, so
        // maneuver type reads at a glance — color (see .sf-markicon--tack/
        // --gybe/--course_change) plus the type's first letter (from the
        // already-translated mark_role, so it's correctly localized).
        // iconSize/iconAnchor both use the FULL 26×33 box (26px circle + 7px
        // tail, see .sf-markicon--maneuver-circle/-tail) — anchor at its
        // bottom-center, the standard Leaflet pin convention. The earlier
        // version anchored past its own (circle-only) iconSize, which is
        // what put the tip in the wrong place.
        const typeClass = mk.maneuverType ? ` sf-markicon--${mk.maneuverType}` : "";
        const pendingClass = mk.kind === "maneuver-pending" ? " sf-markicon--pending" : "";
        icon = L.divIcon({
          className: `sf-markicon sf-markicon--maneuver${typeClass}${pendingClass}`,
          html:
            `<span class="sf-markicon--maneuver-circle">` +
            `<span>${mk.mark_role.charAt(0).toUpperCase()}</span></span>` +
            `<span class="sf-markicon--maneuver-tail"></span>`,
          iconSize: [26, 33],
          iconAnchor: [13, 33],
        });
      } else if (mk.kind === "maneuver-draft") {
        icon = L.divIcon({ className: "sf-markicon sf-markicon--preview", html: "◆", iconSize: [12, 12] });
      } else {
        icon = L.divIcon({
          className: mk.preview ? "sf-markicon sf-markicon--preview" : "sf-markicon",
          html: "◆",
          iconSize: [16, 16],
        });
      }
      L.marker([mk.lat, mk.lng], { icon }).bindTooltip(mk.mark_role).addTo(layer);
    }
    marksLayerRef.current = layer;
    return () => {
      layer.remove();
    };
  }, [marks, tracks]);

  // Move position markers to the cursor time (skipping any mid-drag).
  useEffect(() => {
    cursorRef.current = cursor;
    for (const tr of tracks) {
      if (draggingRef.current.has(tr.id)) continue;
      const marker = markersRef.current[tr.id];
      if (!marker) continue;
      const p = pointAt(tr, cursor);
      if (p) marker.setLatLng([p.lat, p.lon]);
    }
  }, [cursor, tracks]);

  return (
    <div className={`${className} sf-map`}>
      <div ref={elRef} className="sf-map__surface" />
      {mapOptions && <div className="sf-map__options">{mapOptions}</div>}
      {controls && <div className="sf-map__controls">{controls}</div>}
      {displayWind?.twd_deg != null && (
        <div className="sf-map__wind" title={fmtKnots(displayWind.tws_kts)}>
          <span
            className="sf-map__wind-arrow"
            // twd_deg is where the wind comes FROM; rotate by +180 so the
            // arrow shows the direction it's blowing TOWARD (flow), not the
            // bearing to its source.
            style={{ transform: `rotate(${(displayWind.twd_deg + 180) % 360}deg)` }}
          >
            ↑
          </span>
          <span className="sf-map__wind-speed">{fmtKnots(displayWind.tws_kts)}</span>
        </div>
      )}
    </div>
  );
}
