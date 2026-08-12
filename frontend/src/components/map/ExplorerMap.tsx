import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { LocateFixed } from "lucide-react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Button } from "@/components/ui/Button";
import { useMapCenterWind } from "@/hooks/useMapCenterWind";
import { WindBadge } from "./WindBadge";
import { createBaseLayers } from "./baseLayers";
import { MapLayerToggles } from "./MapLayerToggles";
import { useMapLayers } from "./useMapLayers";
import { useNauticalLayers } from "./useNauticalLayers";
import styles from "./ExplorerMap.module.css";

const VIEW_KEY = "xgsail.map.lastView";
// Whole-world view: no hardcoded geography, same principle as MapView (which
// fits its data instead of assuming where the user sails).
const WORLD_VIEW: { lat: number; lng: number; zoom: number } = { lat: 20, lng: 0, zoom: 2 };

function readStoredView(): { lat: number; lng: number; zoom: number } {
  try {
    const raw = localStorage.getItem(VIEW_KEY);
    if (raw) return JSON.parse(raw) as { lat: number; lng: number; zoom: number };
  } catch {
    // Ignore a malformed entry and start from the world view.
  }
  return WORLD_VIEW;
}

/** A plain browsable map — no track, no playback — with the nautical overlays
 * and a "where am I" control. Used as the exploration view in /registra and
 * as the picker surface behind LocationPicker.
 *
 * Separate from components/race/MapView on purpose: that one exists to replay
 * recorded tracks against a time cursor, and everything in it (playback
 * markers, speed-colored polylines, the recenter-on-cursor control) assumes
 * there is a track. The two share what actually is shared — tile layers and
 * the nautical overlays — via baseLayers/useNauticalLayers. */
export function ExplorerMap({
  className = "",
  center,
  zoom,
  marker,
  onPick,
  fill,
  dataTour,
}: {
  className?: string;
  /** Initial center; falls back to the last view this device looked at. */
  center?: { lat: number; lng: number } | null;
  zoom?: number;
  /** A draggable pin to show (picker mode) — omit for a plain map. */
  marker?: { lat: number; lng: number } | null;
  /** Enables picker mode: clicking the map or dragging the pin reports a
   * position. Omit for a read-only map. */
  onPick?: (lat: number, lng: number) => void;
  /** Full-height, edge-to-edge variant (e.g. for a full-screen map page). */
  fill?: boolean;
  /** Anchor for a guided-tour step (see onboarding/tours.ts). */
  dataTour?: string;
}) {
  const { t } = useTranslation();
  const elRef = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const meRef = useRef<L.LayerGroup | null>(null);
  const onPickRef = useRef(onPick);
  onPickRef.current = onPick;
  const [locating, setLocating] = useState(false);
  const [locateError, setLocateError] = useState(false);

  const { layers, toggle } = useMapLayers();
  useNauticalLayers(map, layers);
  // No `at`: this map is about now, not about a recorded moment.
  const wind = useMapCenterWind(map);

  // One-time setup. Deliberately has no data dependencies: unlike MapView,
  // nothing here is rebuilt when props change — later effects mutate the
  // existing map instead.
  useEffect(() => {
    if (!elRef.current) return;
    const instance = L.map(elRef.current, { zoomControl: false, preferCanvas: true });
    L.control.zoom({ position: "bottomright" }).addTo(instance);
    createBaseLayers().base.addTo(instance);

    const start = center ? { ...center, zoom: zoom ?? 13 } : readStoredView();
    instance.setView([start.lat, start.lng], zoom ?? start.zoom);

    instance.on("moveend", () => {
      const c = instance.getCenter();
      localStorage.setItem(
        VIEW_KEY,
        JSON.stringify({ lat: c.lat, lng: c.lng, zoom: instance.getZoom() }),
      );
    });
    instance.on("click", (e: L.LeafletMouseEvent) => {
      onPickRef.current?.(e.latlng.lat, e.latlng.lng);
    });

    setMap(instance);
    return () => {
      instance.remove();
      markerRef.current = null;
      meRef.current = null;
      setMap(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initial view only:
    // later center/zoom changes are applied by the effect below, not by a rebuild.
  }, []);

  // The picked position, as a draggable pin.
  useEffect(() => {
    if (!map) return;
    if (!marker) {
      if (markerRef.current) {
        map.removeLayer(markerRef.current);
        markerRef.current = null;
      }
      return;
    }
    if (!markerRef.current) {
      const m = L.marker([marker.lat, marker.lng], {
        draggable: !!onPick,
        icon: L.divIcon({
          className: styles.pin,
          html: `<span class="${styles.pinDot}"></span>`,
          iconSize: [18, 18],
          iconAnchor: [9, 9],
        }),
      }).addTo(map);
      m.on("dragend", () => {
        const p = m.getLatLng();
        onPickRef.current?.(p.lat, p.lng);
      });
      markerRef.current = m;
    } else {
      markerRef.current.setLatLng([marker.lat, marker.lng]);
    }
  }, [map, marker, onPick]);

  // Keep the view on an externally-controlled center (e.g. a geocoding result
  // dropping the pin somewhere else entirely).
  useEffect(() => {
    if (map && center) map.setView([center.lat, center.lng], zoom ?? map.getZoom());
  }, [map, center, zoom]);

  const locate = () => {
    if (!map || !navigator.geolocation) {
      setLocateError(true);
      return;
    }
    setLocating(true);
    setLocateError(false);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        const { latitude, longitude, accuracy } = pos.coords;
        meRef.current?.remove();
        meRef.current = L.layerGroup([
          L.circle([latitude, longitude], { radius: accuracy, ...ACCURACY_STYLE }),
          L.circleMarker([latitude, longitude], { radius: 6, ...DOT_STYLE }),
        ]).addTo(map);
        map.setView([latitude, longitude], Math.max(map.getZoom(), 14));
      },
      () => {
        setLocating(false);
        setLocateError(true);
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };

  return (
    <div className={`${styles.map} ${fill ? styles.mapFill : ""} ${className}`} data-tour={dataTour}>
      <div ref={elRef} className={styles.surface} />
      <WindBadge twdDeg={wind?.twd_deg} twsKts={wind?.tws_kts} className={styles.wind} />
      <div className={styles.options}>
        <MapLayerToggles layers={layers} onToggle={toggle} />
      </div>
      <div className={styles.locate}>
        <Button
          type="button"
          className="sf-btn--icon"
          variant="ghost"
          disabled={locating}
          aria-label={t("map.locate")}
          title={locateError ? t("map.locateError") : t("map.locate")}
          onClick={locate}
        >
          <LocateFixed size={18} strokeWidth={1.75} />
        </Button>
      </div>
    </div>
  );
}

const ACCURACY_STYLE = { color: "#2f9be0", weight: 1, fillOpacity: 0.12 };
const DOT_STYLE = { color: "#fff", weight: 2, fillColor: "#2f9be0", fillOpacity: 1 };
