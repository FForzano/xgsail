import { api } from "@/api/client";
import type { Mark, Race, RaceData, RaceDay, RaceResult, Regatta, Session, UUID } from "@/types";

export const raceKeys = {
  regattas: ["regattas"] as const,
  regatta: (id: UUID) => ["regattas", id] as const,
  raceday: (id: UUID) => ["racedays", id] as const,
  race: (id: UUID) => ["races", id] as const,
  data: (id: UUID) => ["races", id, "data"] as const,
};

export const regattasService = {
  list: (clubId?: UUID) => api.get<Regatta[]>(`/regattas${clubId ? `?club_id=${clubId}` : ""}`),
  get: (id: UUID) => api.get<Regatta>(`/regattas/${id}`), // embeds race_days
  create: (body: Partial<Regatta>) => api.post<Regatta>("/regattas", body),
  update: (id: UUID, body: Partial<Regatta>) => api.patch<Regatta>(`/regattas/${id}`, body),
  remove: (id: UUID) => api.del(`/regattas/${id}`),
};

export const racedaysService = {
  get: (id: UUID) => api.get<RaceDay>(`/racedays/${id}`), // embeds races
  create: (body: Partial<RaceDay>) => api.post<RaceDay>("/racedays", body),
  update: (id: UUID, body: Partial<RaceDay>) => api.patch<RaceDay>(`/racedays/${id}`, body),
  remove: (id: UUID) => api.del(`/racedays/${id}`),
};

export const racesService = {
  get: (id: UUID) => api.get<Race>(`/races/${id}`), // embeds activity_id + results
  create: (body: Partial<Race>) => api.post<Race>("/races", body),
  update: (id: UUID, body: Partial<Race>) => api.patch<Race>(`/races/${id}`, body),
  remove: (id: UUID) => api.del(`/races/${id}`),

  results: (id: UUID) => api.get<RaceResult[]>(`/races/${id}/results`),
  upsertResult: (id: UUID, boatId: UUID, body: Partial<RaceResult>) =>
    api.put<RaceResult>(`/races/${id}/results/${boatId}`, body),
  removeResult: (id: UUID, boatId: UUID) => api.del(`/races/${id}/results/${boatId}`),

  data: (id: UUID, opts: { sensors?: string; padStart?: number; padEnd?: number } = {}) =>
    api.get<RaceData>(
      `/races/${id}/data?sensors=${opts.sensors ?? "gps"}` +
        `&pad_start=${opts.padStart ?? 120}&pad_end=${opts.padEnd ?? 120}`,
    ),

  matchSessions: (id: UUID) =>
    api.post<{ ok: boolean; matched: Session[] }>(`/races/${id}/match-sessions`),
  autoStartLine: (id: UUID, apply: boolean) =>
    api.post<{ marks?: Mark[]; pin?: unknown; rc?: unknown }>(
      `/races/${id}/auto-start-line?apply=${apply}`,
    ),
  suggestMarks: (id: UUID, apply: boolean) =>
    api.post<{ marks: Array<Partial<Mark>> }>(`/races/${id}/suggest-marks?apply=${apply}`),

  uploadBoatGpx: (id: UUID, boatId: UUID, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post(`/races/${id}/boats/${boatId}/gpx`, form);
  },
};
