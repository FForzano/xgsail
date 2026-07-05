import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useTimeState } from "@/stores/timeController";
import { pointAt, type Track } from "./raceModel";

export interface MapMark {
  id?: string;
  mark_role: string;
  lat: number;
  lng: number;
  /** preview marks (suggest/auto-start-line before apply) render dashed */
  preview?: boolean;
}

// Imperative Leaflet (not react-leaflet): tracks + marks are drawn once, and
// only the per-boat position markers move on every cursor tick — kept in refs
// so playback doesn't churn React's tree. No hardcoded geography: the view
// always fits the data; with no data it shows a neutral world view.
export function MapView({
  tracks,
  marks = [],
  className = "sf-race__map",
}: {
  tracks: Track[];
  marks?: MapMark[];
  className?: string;
}) {
  const elRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<Record<string, L.CircleMarker>>({});
  const { cursor } = useTimeState();

  // One-time map + static layer setup (rebuilt when the data identity changes).
  useEffect(() => {
    if (!elRef.current) return;
    const map = L.map(elRef.current, { zoomControl: true });
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      attribution: "© OpenStreetMap © CARTO",
      maxZoom: 20,
    }).addTo(map);
    mapRef.current = map;

    const bounds: L.LatLngExpression[] = [];
    for (const tr of tracks) {
      const latlngs = tr.pts.map((p) => [p.lat, p.lon] as [number, number]);
      if (!latlngs.length) continue;
      L.polyline(latlngs, { color: tr.color, weight: 2, opacity: 0.8 }).addTo(map);
      bounds.push(...latlngs);
      const m = L.circleMarker(latlngs[0], {
        radius: 6,
        color: "#fff",
        weight: 2,
        fillColor: tr.color,
        fillOpacity: 1,
      });
      m.bindTooltip(tr.name);
      m.addTo(map);
      markersRef.current[tr.id] = m;
    }

    for (const mk of marks) {
      L.marker([mk.lat, mk.lng], {
        icon: L.divIcon({
          className: mk.preview ? "sf-markicon sf-markicon--preview" : "sf-markicon",
          html: "◆",
          iconSize: [16, 16],
        }),
      })
        .bindTooltip(mk.mark_role)
        .addTo(map);
      bounds.push([mk.lat, mk.lng]);
    }

    if (bounds.length) map.fitBounds(L.latLngBounds(bounds).pad(0.1));
    else map.setView([20, 0], 2); // neutral world view when there is no data

    return () => {
      map.remove();
      mapRef.current = null;
      markersRef.current = {};
    };
  }, [tracks, marks]);

  // Move position markers to the cursor time.
  useEffect(() => {
    for (const tr of tracks) {
      const marker = markersRef.current[tr.id];
      if (!marker) continue;
      const p = pointAt(tr, cursor);
      if (p) marker.setLatLng([p.lat, p.lon]);
    }
  }, [cursor, tracks]);

  return <div ref={elRef} className={className} />;
}
