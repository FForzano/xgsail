import { api } from "@/api/client";
import type {
  ImageUploadTicket,
  Mark,
  Race,
  RaceData,
  RaceDay,
  RaceResult,
  Regatta,
  RegattaEntry,
  RegattaStandings,
  Session,
  UUID,
} from "@/types";

export const raceKeys = {
  regattas: ["regattas"] as const,
  regatta: (id: UUID) => ["regattas", id] as const,
  entries: (id: UUID) => ["regattas", id, "entries"] as const,
  joinCode: (id: UUID) => ["regattas", id, "join-code"] as const,
  standings: (id: UUID) => ["regattas", id, "standings"] as const,
  raceday: (id: UUID) => ["racedays", id] as const,
  race: (id: UUID) => ["races", id] as const,
  data: (id: UUID) => ["races", id, "data"] as const,
};

export const regattasService = {
  list: (opts: { clubId?: UUID; mine?: boolean; memberClubs?: boolean } = {}) => {
    const params = new URLSearchParams();
    if (opts.clubId) params.set("club_id", opts.clubId);
    if (opts.mine) params.set("mine", "true");
    if (opts.memberClubs) params.set("member_clubs", "true");
    const qs = params.toString();
    return api.get<Regatta[]>(`/regattas${qs ? `?${qs}` : ""}`);
  },
  get: (id: UUID) => api.get<Regatta>(`/regattas/${id}`), // embeds race_days, each with its races
  create: (body: Partial<Regatta>) => api.post<Regatta>("/regattas", body),
  update: (id: UUID, body: Partial<Regatta>) => api.patch<Regatta>(`/regattas/${id}`, body),
  remove: (id: UUID) => api.del(`/regattas/${id}`),

  uploadImage: (id: UUID) => api.post<ImageUploadTicket>(`/regattas/${id}/image`),
  confirmImage: (id: UUID, imageId: UUID) => api.post(`/regattas/${id}/image/${imageId}/confirm`),

  // Start list. Being on it is what lets a sailor tag a recording with one of
  // this regatta's races, so it is not organizer-only: `join` is the
  // self-service path for boats the organizer hasn't entered by hand.
  entries: (id: UUID) => api.get<RegattaEntry[]>(`/regattas/${id}/entries`),
  addEntry: (id: UUID, boatId: UUID) =>
    api.post<RegattaEntry>(`/regattas/${id}/entries`, { boat_id: boatId }),
  removeEntry: (id: UUID, boatId: UUID) => api.del(`/regattas/${id}/entries/${boatId}`),
  join: (id: UUID, body: { code: string; boat_id: UUID }) =>
    api.post<RegattaEntry>(`/regattas/${id}/join`, body),

  // Series standings, computed server-side. Public like the rest of a
  // regatta's read surface — no manage permission needed.
  standings: (id: UUID) => api.get<RegattaStandings>(`/regattas/${id}/standings`),

  joinCode: (id: UUID) => api.get<{ join_code: string | null }>(`/regattas/${id}/join-code`),
  regenerateJoinCode: (id: UUID) =>
    api.post<{ join_code: string }>(`/regattas/${id}/join-code`),
  revokeJoinCode: (id: UUID) => api.del(`/regattas/${id}/join-code`),
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
