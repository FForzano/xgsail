import { api } from "@/api/client";
import type { UUID, WindObservation, WindSnapshot, WindStation } from "@/types";

export const windKeys = {
  stations: ["wind", "stations"] as const,
  observations: (id: UUID, params = "") => ["wind", "stations", id, "observations", params] as const,
  nearest: (lat: number, lng: number, at?: string) => ["wind", "nearest", lat, lng, at ?? "now"] as const,
};

export const windService = {
  listStations: () => api.get<WindStation[]>("/wind/stations"),
  createStation: (body: Partial<WindStation>) => api.post<WindStation>("/wind/stations", body),
  updateStation: (id: UUID, body: Partial<WindStation>) =>
    api.patch<WindStation>(`/wind/stations/${id}`, body),
  removeStation: (id: UUID) => api.del(`/wind/stations/${id}`),
  /** Newest-first, paginated (default: last 72h server-side, 200 rows). */
  observations: (id: UUID, opts: { start?: string; end?: string; limit?: number; offset?: number } = {}) => {
    const p = new URLSearchParams();
    if (opts.start) p.set("start", opts.start);
    if (opts.end) p.set("end", opts.end);
    if (opts.limit) p.set("limit", String(opts.limit));
    if (opts.offset) p.set("offset", String(opts.offset));
    const s = p.toString();
    return api.get<WindObservation[]>(`/wind/stations/${id}/observations${s ? `?${s}` : ""}`);
  },
  /** Quick live value for WindCard/map display — a real station in range
   * wins if it has data near `at`, otherwise an unblended Open-Meteo
   * candidate. NOT the per-session determined wind estimate — nothing here
   * is persisted. Any authenticated user. */
  nearest: (lat: number, lng: number, at?: string) => {
    const p = new URLSearchParams({ lat: String(lat), lng: String(lng) });
    if (at) p.set("at", at);
    return api.get<WindSnapshot>(`/wind/nearest?${p.toString()}`);
  },
};
