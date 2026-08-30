import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type L from "leaflet";
import { fetchNauticalPoi, type Bbox, type NauticalPoi } from "@/services/nauticalPoi";

/** Below this the visible area is whole seas wide — the query would return
 * thousands of elements and the pins would be unreadable anyway. This hook is
 * what enforces it for the POIs; the weather-station layer is gated on the
 * same number, which is why the constant is named for the tier rather than
 * for the POIs and is exported: one gate, one number, explained once in the
 * switcher. */
export const NEAR_DETAIL_MIN_ZOOM = 11;
/** Snap the bbox to this grid (degrees) so panning around the same area keeps
 * hitting the same cache entry instead of issuing a query per pixel moved —
 * both our TanStack cache and the backend's per-cell cache benefit. */
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

/** Nautical POIs for whatever the map is currently showing, served by our own
 * backend (which owns the Overpass fetch and caches it per cell — see
 * services/nauticalPoi.ts). Nothing is requested until the user is zoomed in
 * past NEAR_DETAIL_MIN_ZOOM, movements are debounced, and the bbox is snapped
 * to a grid so a normal browsing session hits the cache instead of issuing a
 * request per pan. */
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
    queryKey: ["nautical-poi", bbox],
    queryFn: ({ signal }) => fetchNauticalPoi(bbox!, signal),
    enabled: enabled && !!bbox,
    staleTime: 30 * 60 * 1000,
    gcTime: 2 * 60 * 60 * 1000,
    // A missing overlay is a soft failure — the map itself still works — so
    // one retry is enough rather than hammering our own backend.
    retry: 1,
    refetchOnWindowFocus: false,
  });

  // "failed" means "we could not find out what is here", which is now two
  // cases: the request itself errored, or it succeeded but the backend
  // reports partial coverage (a cell it hasn't fetched from Overpass yet) —
  // either way the caller can't tell "no pins" from "nothing here" without
  // this flag.
  const coverage = query.data?.coverage;
  return { pois: query.data?.pois ?? [], failed: query.isError || coverage === "partial" };
}
