/** Address → coordinates via Nominatim (OpenStreetMap's public geocoder).
 *
 * Nominatim's usage policy caps callers at ~1 request/second and forbids bulk
 * or automatic querying, so this is only ever called from an explicit user
 * action (the "find from address" button in LocationPicker) — never on typing,
 * blur or form load. Like the tile and Overpass hosts, it is contacted
 * directly by the browser; see the third-party map services section of
 * frontend/src/content/legal/privacy.ts. */

const ENDPOINT = "https://nominatim.openstreetmap.org/search";

export interface AddressParts {
  addressLine1?: string | null;
  city?: string | null;
  postalCode?: string | null;
  stateProvince?: string | null;
  country?: string | null;
}

export interface GeocodeResult {
  lat: number;
  lng: number;
  displayName: string;
}

/** Returns the single best match, or null when the address yields nothing. */
export async function geocodeAddress(
  parts: AddressParts,
  language?: string,
): Promise<GeocodeResult | null> {
  const q = [parts.addressLine1, parts.postalCode, parts.city, parts.stateProvince, parts.country]
    .map((s) => s?.trim())
    .filter(Boolean)
    .join(", ");
  if (!q) return null;

  const url = `${ENDPOINT}?${new URLSearchParams({ format: "jsonv2", limit: "1", q })}`;
  const res = await fetch(url, {
    headers: language ? { "Accept-Language": language } : undefined,
  });
  if (!res.ok) throw new Error(`Nominatim ${res.status}`);
  const rows = (await res.json()) as Array<{ lat: string; lon: string; display_name: string }>;
  const first = rows[0];
  if (!first) return null;
  return { lat: Number(first.lat), lng: Number(first.lon), displayName: first.display_name };
}
