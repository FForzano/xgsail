import { useCallback } from "react";
import { usePersistentState } from "@/hooks/usePersistentState";

export interface MapLayers {
  /** OpenSeaMap's nautical raster overlay (buoys, lights, depths). */
  seamark: boolean;
  /** Nautical points of interest from Overpass (marinas, harbours, …). */
  poi: boolean;
  /** XGSail clubs that have coordinates set. */
  clubs: boolean;
  /** Real weather stations feeding the wind estimate. */
  stations: boolean;
}

export const DEFAULT_MAP_LAYERS: MapLayers = {
  seamark: false,
  poi: false,
  clubs: false,
  stations: false,
};

/** Defaults for the explorer/registra map: all four overlays on, since the map
 * is for finding where to sail and the overlays are the point. The replay map
 * keeps everything off by default, where overlays would clutter the view of
 * the recorded track. */
export const EXPLORER_MAP_LAYERS: MapLayers = {
  seamark: true,
  poi: true,
  clubs: true,
  stations: true,
};

/** Clubs are point data spread over the whole world, so at a continental zoom
 * they collapse into an unreadable field of pins that says nothing about
 * anywhere. Below this zoom the layer stays off even when toggled on, and the
 * switcher says so (see useNauticalLayers/MapLayerToggles).
 *
 * Clubs get the lowest of the gates on purpose — they are the layer worth
 * spotting from furthest out. Weather stations sit at the POI gate instead
 * (NEAR_DETAIL_MIN_ZOOM), and the seamark layer has none at all: it is raster
 * tiles, which thin themselves out by zoom already. */
export const CLUBS_MIN_ZOOM = 9;

const STORAGE_KEY = "xgsail.map.layers";

/** Which optional map overlays are on, remembered across pages and reloads so
 * a user who sails with the nautical chart on doesn't re-enable it every time
 * they open a session. Device-local (see usePersistentState).
 *
 * @param options.defaults - Which layers are on by default (DEFAULT_MAP_LAYERS for replay, EXPLORER_MAP_LAYERS for explorer)
 * @param options.storageKey - localStorage key for persistence (different per context to prevent cross-map leakage)
 */
export function useMapLayers(options?: {
  defaults?: MapLayers;
  storageKey?: string;
}): {
  layers: MapLayers;
  toggle: (key: keyof MapLayers, on: boolean) => void;
} {
  const defaults = options?.defaults ?? DEFAULT_MAP_LAYERS;
  const key = options?.storageKey ?? STORAGE_KEY;

  const [stored, setStored] = usePersistentState<MapLayers>(key, defaults);
  // Spread over the defaults so a key added in a later release doesn't come
  // back `undefined` for users with an older object already persisted.
  const layers = { ...defaults, ...stored };

  const toggle = useCallback(
    (key: keyof MapLayers, on: boolean) => {
      setStored({ ...defaults, ...stored, [key]: on });
    },
    [stored, setStored, defaults],
  );

  return { layers, toggle };
}
