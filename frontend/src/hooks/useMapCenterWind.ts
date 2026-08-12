import { useEffect, useState } from "react";
import type L from "leaflet";
import { useWindAt } from "@/hooks/useWindAt";
import { roundCoord } from "@/utils/geo";
import type { WindSnapshot } from "@/types";

/** Wind at whatever the map is currently looking at — the center is re-read on
 * `moveend`, so panning/zooming moves the reading with the view.
 *
 * No debounce on purpose: `moveend` already fires once a gesture settles, the
 * coordinate is coarsened to ~1 km (so small pans reuse the same query key),
 * and TanStack Query holds the result for 15 minutes.
 *
 * @param at Instant to look up (a session's start time) — omit for wind now.
 * @param fallback Center to use until the map instance exists, so a map with a
 *   known subject (a recorded track) shows the badge on first paint.
 */
export function useMapCenterWind(
  map: L.Map | null,
  at?: string | null,
  fallback?: { lat: number; lng: number } | null,
): WindSnapshot | null {
  const [center, setCenter] = useState<{ lat: number; lng: number } | null>(null);

  useEffect(() => {
    if (!map) {
      setCenter(null);
      return;
    }
    const read = () => {
      const c = map.getCenter();
      const next = { lat: roundCoord(c.lat), lng: roundCoord(c.lng) };
      // Keep the previous object when the coarsened position is unchanged —
      // a new identity here would be a new query key for the same coordinate.
      setCenter((prev) => (prev && prev.lat === next.lat && prev.lng === next.lng ? prev : next));
    };
    read();
    map.on("moveend", read);
    return () => {
      map.off("moveend", read);
    };
  }, [map]);

  const source = center ?? (fallback ? { lat: roundCoord(fallback.lat), lng: roundCoord(fallback.lng) } : null);
  const { data } = useWindAt(source?.lat, source?.lng, at);
  return data;
}
