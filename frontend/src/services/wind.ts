import { api } from "@/api/client";
import type { UUID, WindObservation, WindStation } from "@/types";

export const windKeys = {
  stations: ["wind", "stations"] as const,
  observations: (id: UUID) => ["wind", "stations", id, "observations"] as const,
};

export const windService = {
  listStations: () => api.get<WindStation[]>("/wind/stations"),
  createStation: (body: Partial<WindStation>) => api.post<WindStation>("/wind/stations", body),
  updateStation: (id: UUID, body: Partial<WindStation>) =>
    api.patch<WindStation>(`/wind/stations/${id}`, body),
  removeStation: (id: UUID) => api.del(`/wind/stations/${id}`),
  observations: (id: UUID, start?: string, end?: string) => {
    const p = new URLSearchParams();
    if (start) p.set("start", start);
    if (end) p.set("end", end);
    const s = p.toString();
    return api.get<WindObservation[]>(`/wind/stations/${id}/observations${s ? `?${s}` : ""}`);
  },
};
