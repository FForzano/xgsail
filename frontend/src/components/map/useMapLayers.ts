import { useCallback } from "react";
import { usePersistentState } from "@/hooks/usePersistentState";

export interface MapLayers {
  /** OpenSeaMap's nautical raster overlay (buoys, lights, depths). */
  seamark: boolean;
  /** Nautical points of interest from Overpass (marinas, harbours, …). */
  poi: boolean;
  /** XGSail clubs that have coordinates set. */
  clubs: boolean;
}

export const DEFAULT_MAP_LAYERS: MapLayers = { seamark: false, poi: false, clubs: false };

const STORAGE_KEY = "xgsail.map.layers";

/** Which optional map overlays are on, remembered across pages and reloads so
 * a user who sails with the nautical chart on doesn't re-enable it every time
 * they open a session. Device-local (see usePersistentState). */
export function useMapLayers(): {
  layers: MapLayers;
  toggle: (key: keyof MapLayers, on: boolean) => void;
} {
  const [stored, setStored] = usePersistentState<MapLayers>(STORAGE_KEY, DEFAULT_MAP_LAYERS);
  // Spread over the defaults so a key added in a later release doesn't come
  // back `undefined` for users with an older object already persisted.
  const layers = { ...DEFAULT_MAP_LAYERS, ...stored };

  const toggle = useCallback(
    (key: keyof MapLayers, on: boolean) => {
      setStored({ ...DEFAULT_MAP_LAYERS, ...stored, [key]: on });
    },
    [stored, setStored],
  );

  return { layers, toggle };
}
