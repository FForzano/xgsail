import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type L from "leaflet";
import { fetchNauticalPoi, type Bbox, type NauticalPoi } from "@/services/overpass";

/** Below this the visible area is whole seas wide — the query would return
 * thousands of elements and the pins would be unreadable anyway. This hook is
 * what enforces it for the POIs (Overpass's rate limits are the binding
 * reason), but the weather-station layer is gated on the same number, which
 * is why the constant is named for the tier rather than for the POIs and is
 * exported: one gate, one number, explained once in the switcher. */
export const NEAR_DETAIL_MIN_ZOOM = 11;
/** Snap the bbox to this grid (degrees) so panning around the same area keeps
 * hitting the same cache entry instead of issuing a query per pixel moved. */
const BBOX_STEP = 0.05;
const DEBOUNCE_MS = 500;

function snapBbox(b: L.LatLngBounds): Bbox {
  const floor = (v: number) => Math.floor(v / BBOX_STEP) * BBOX_STEP;
  const ceil = (v: number) => Math.ceil(v / BBOX_STEP) * BBOX_STEP;
  return [
    Number(floor(b.getSouth()).toFixed(3)),
    Number(floor(b.getWest()).toFixed(3)),
    Number(ceil(b.getNorth()).toFixed(3)),
    Number(ceil(b.getEast()).toFixed(3)),
  ];
}

/** Nautical POIs for whatever the map is currently showing. Deliberately
 * conservative about hitting Overpass (see services/overpass.ts): nothing is
 * requested until the user is zoomed in past NEAR_DETAIL_MIN_ZOOM, movements are
 * debounced, the bbox is snapped to a grid, and results are cached long enough
 * that a normal browsing session issues a handful of requests, not one per
 * pan. */
export function useNauticalPoi(
  map: L.Map | null,
  enabled: boolean,
): { pois: NauticalPoi[]; failed: boolean } {
  const [bbox, setBbox] = useState<Bbox | null>(null);

  useEffect(() => {
    if (!map || !enabled) {
      setBbox(null);
      return;
    }
    let timer: ReturnType<typeof setTimeout>;
    const update = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        setBbox(map.getZoom() >= NEAR_DETAIL_MIN_ZOOM ? snapBbox(map.getBounds()) : null);
      }, DEBOUNCE_MS);
    };
    update();
    map.on("moveend", update);
    return () => {
      clearTimeout(timer);
      map.off("moveend", update);
    };
  }, [map, enabled]);

  const query = useQuery({
    queryKey: ["overpass", "nautical-poi", bbox],
    queryFn: ({ signal }) => fetchNauticalPoi(bbox!, signal),
    enabled: enabled && !!bbox,
    staleTime: 30 * 60 * 1000,
    gcTime: 2 * 60 * 60 * 1000,
    // Overpass answers 429/504 when busy; hammering it makes that worse, and
    // a missing overlay is a soft failure — the map itself still works.
    retry: 1,
    refetchOnWindowFocus: false,
  });

  // The failure is reported rather than swallowed: this layer has exactly one
  // upstream, and a volunteer-run one that does go down, so "no pins" would
  // otherwise be indistinguishable from "nothing here" — the same silent
  // emptiness the zoom gate used to produce.
  return { pois: query.data ?? [], failed: query.isError };
}
