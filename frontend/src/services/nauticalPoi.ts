/** Nautical points of interest from OpenStreetMap. Fetched via the backend's
 * `/osm-poi` endpoint (`backend/services/osm_poi.py`), which owns the actual
 * Overpass query, tag classification, and per-cell caching — see that module
 * for the rules on what counts as a marina/harbour/etc. This file only shapes
 * the request and response for the map layer. */

import { api } from "@/api/client";

export type PoiKind =
  | "marina"
  | "harbour"
  | "slipway"
  | "sailing_club"
  | "sports_area"
  | "fuel"
  | "anchorage";

export interface NauticalPoi {
  /** Stable across refetches: OSM element type + id (`osm_ref`). Also what
   * the map dedupes claimed clubs against (Club.osm_ref), so it must keep
   * comparing equal to that value. */
  id: string;
  kind: PoiKind;
  lat: number;
  lng: number;
  name: string | null;
  /** OSM element type + numeric id, for the "view on OSM" popup link —
   * derived from `id`, which the backend sends as a single "{type}/{id}"
   * string. */
  osmType: string;
  osmId: number;
}

/** [south, west, north, east] — matches the backend's `bbox` query param
 * order. */
export type Bbox = [number, number, number, number];

interface OsmPoiResponseItem {
  osm_ref: string;
  kind: PoiKind;
  lat: number;
  lng: number;
  name: string | null;
}

interface OsmPoiResponse {
  pois: OsmPoiResponseItem[];
  coverage: "complete" | "partial";
}

export interface NauticalPoiResult {
  pois: NauticalPoi[];
  /** True when some cell overlapping the bbox hasn't been successfully
   * fetched yet — lets the caller distinguish "nothing here" from "we
   * couldn't find out". */
  coverage: "complete" | "partial";
}

export async function fetchNauticalPoi(bbox: Bbox, signal?: AbortSignal): Promise<NauticalPoiResult> {
  const [south, west, north, east] = bbox;
  const params = new URLSearchParams({ bbox: `${south},${west},${north},${east}` });
  const json = await api.get<OsmPoiResponse>(`/osm-poi?${params.toString()}`, { signal });
  const pois = json.pois.map((item) => {
    const [osmType, osmIdStr] = item.osm_ref.split("/");
    return {
      id: item.osm_ref,
      kind: item.kind,
      lat: item.lat,
      lng: item.lng,
      name: item.name,
      osmType,
      osmId: Number(osmIdStr),
    };
  });
  return { pois, coverage: json.coverage };
}
