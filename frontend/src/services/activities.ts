import { api } from "@/api/client";
import type { Activity, ActivityData, ActivityStatus, Mark, Session, UUID } from "@/types";

export const activityKeys = {
  all: ["activities"] as const,
  list: (filters: Record<string, string>) => ["activities", filters] as const,
  detail: (id: UUID) => ["activities", id] as const,
  sessions: (id: UUID) => ["activities", id, "sessions"] as const,
  marks: (id: UUID) => ["activities", id, "marks"] as const,
  data: (id: UUID) => ["activities", id, "data"] as const,
};

function qs(params: Record<string, string | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const activitiesService = {
  list: (
    filters: {
      type?: string;
      club_id?: UUID;
      group_id?: UUID;
      status?: ActivityStatus;
      mine?: boolean;
    } = {},
  ) =>
    api.get<Activity[]>(
      `/activities${qs({ ...filters, mine: filters.mine ? "true" : undefined })}`,
    ),
  get: (id: UUID) => api.get<Activity>(`/activities/${id}`),
  create: (body: Partial<Activity>) => api.post<Activity>("/activities", body),
  update: (id: UUID, body: Partial<Activity>) => api.patch<Activity>(`/activities/${id}`, body),
  remove: (id: UUID) => api.del(`/activities/${id}`),

  sessions: (id: UUID) => api.get<Session[]>(`/activities/${id}/sessions`),
  regenerateThumbnail: (id: UUID) => api.post<{ ok: boolean }>(`/activities/${id}/regenerate-thumbnail`),
  data: (id: UUID, opts: { sensors?: string; padStart?: number; padEnd?: number } = {}) =>
    api.get<ActivityData>(
      `/activities/${id}/data?sensors=${opts.sensors ?? "gps"}` +
        `&pad_start=${opts.padStart ?? 120}&pad_end=${opts.padEnd ?? 120}`,
    ),

  marks: (id: UUID) => api.get<Mark[]>(`/activities/${id}/marks`),
  addMark: (id: UUID, body: Partial<Mark>) => api.post<Mark>(`/activities/${id}/marks`, body),
  updateMark: (id: UUID, markId: UUID, body: Partial<Mark>) =>
    api.patch<Mark>(`/activities/${id}/marks/${markId}`, body),
  removeMark: (id: UUID, markId: UUID) => api.del(`/activities/${id}/marks/${markId}`),
};
