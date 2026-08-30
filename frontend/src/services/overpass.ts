/** Nautical points of interest from OpenStreetMap, via the public Overpass
 * API. Queried straight from the browser (no backend proxy): the data is
 * public, unauthenticated, and caching it server-side would mean owning a
 * refresh job for something the map only needs opportunistically.
 *
 * Overpass is a shared community service with real rate limits — every caller
 * must go through useNauticalPoi (hooks/useNauticalPoi.ts), which bounds the
 * request rate by zoom, debounce and a rounded-bbox query cache. */

// Tried in order. It is a volunteer-run service and the main instance does go
// down outright (not just 429) — with a single endpoint that means the layer
// silently renders nothing, so a second instance is worth the four lines. Kept
// short on purpose: fanning out over many mirrors on every failure is exactly
// the load that gets clients blocked.
const ENDPOINTS = [
  "https://overpass-api.de/api/interpreter",
  "https://overpass.kumi.systems/api/interpreter",
];
const TIMEOUT_S = 25;

export type PoiKind =
  | "marina"
  | "harbour"
  | "slipway"
  | "sailing_club"
  | "sports_area"
  | "fuel"
  | "anchorage";

export interface NauticalPoi {
  /** Stable across refetches: OSM element type + id. */
  id: string;
  kind: PoiKind;
  lat: number;
  lng: number;
  name: string | null;
  /** OSM element type + numeric id, for the "view on OSM" popup link. */
  osmType: string;
  osmId: number;
}

/** [south, west, north, east] — Overpass's bbox order. */
export type Bbox = [number, number, number, number];

// Ordered most- to least-specific: an element tagged both `leisure=marina`
// and `harbour=yes` should read as a marina, so the first match wins.
const KIND_RULES: Array<[PoiKind, (tags: Record<string, string>) => boolean]> = [
  ["marina", (tg) => tg.leisure === "marina"],
  ["slipway", (tg) => tg.leisure === "slipway"],
  ["sailing_club", (tg) => tg.club === "sailing" || (tg.sport === "sailing" && !!tg.club)],
  ["anchorage", (tg) => tg["seamark:type"] === "anchorage"],
  ["fuel", (tg) => tg.amenity === "fuel" && !!tg["seamark:type"]],
  ["harbour", (tg) => tg["seamark:type"] === "harbour" || tg.harbour === "yes"],
  ["sports_area", (tg) => tg.sport === "sailing"],
];

// `nwr` covers nodes, ways and relations in one clause; `out center tags`
// collapses ways/relations to a single representative point, which is all a
// map pin needs.
function buildQuery([s, w, n, e]: Bbox): string {
  const bbox = `${s},${w},${n},${e}`;
  const clauses = [
    `nwr["leisure"="marina"](${bbox});`,
    `nwr["leisure"="slipway"](${bbox});`,
    `nwr["club"="sailing"](${bbox});`,
    `nwr["sport"="sailing"](${bbox});`,
    `nwr["seamark:type"="harbour"](${bbox});`,
    `nwr["seamark:type"="anchorage"](${bbox});`,
    `nwr["harbour"="yes"](${bbox});`,
    `nwr["amenity"="fuel"]["seamark:type"](${bbox});`,
  ];
  return `[out:json][timeout:${TIMEOUT_S}];(${clauses.join("")});out center tags;`;
}

interface OverpassElement {
  type: string;
  id: number;
  lat?: number;
  lon?: number;
  center?: { lat: number; lon: number };
  tags?: Record<string, string>;
}

function classify(tags: Record<string, string>): PoiKind | null {
  for (const [kind, matches] of KIND_RULES) {
    if (matches(tags)) return kind;
  }
  return null;
}

/** POSTs the query to each endpoint in turn, returning the first that answers.
 * A caller-side abort is never a failover — it means the map moved on. */
async function queryOverpass(bbox: Bbox, signal?: AbortSignal): Promise<{ elements?: OverpassElement[] }> {
  const body = new URLSearchParams({ data: buildQuery(bbox) });
  let lastError: unknown;
  for (const endpoint of ENDPOINTS) {
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
        signal,
      });
      if (!res.ok) throw new Error(`Overpass ${res.status}`);
      return (await res.json()) as { elements?: OverpassElement[] };
    } catch (error) {
      if (signal?.aborted) throw error;
      lastError = error;
    }
  }
  throw lastError ?? new Error("Overpass unreachable");
}

export async function fetchNauticalPoi(bbox: Bbox, signal?: AbortSignal): Promise<NauticalPoi[]> {
  const json = await queryOverpass(bbox, signal);

  const out: NauticalPoi[] = [];
  for (const el of json.elements ?? []) {
    const lat = el.lat ?? el.center?.lat;
    const lng = el.lon ?? el.center?.lon;
    const tags = el.tags ?? {};
    if (lat == null || lng == null) continue;
    const kind = classify(tags);
    if (!kind) continue;
    const name = tags.name ?? null;
    // An unnamed marina/harbour is still worth a pin; an unnamed generic
    // "sailing area" polygon is just noise on the map.
    if (!name && (kind === "sports_area" || kind === "sailing_club")) continue;
    out.push({ id: `${el.type}/${el.id}`, kind, lat, lng, name, osmType: el.type, osmId: el.id });
  }
  return out;
}
