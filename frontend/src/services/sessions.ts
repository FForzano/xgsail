import { api } from "@/api/client";
import type {
  FileRef,
  FileUploadTicket,
  ImageRef,
  ImageUploadTicket,
  Session,
  SessionCrew,
  SessionStats,
  SessionStream,
  UUID,
} from "@/types";

export const sessionKeys = {
  mine: ["sessions", "mine"] as const,
  detail: (id: UUID) => ["sessions", id] as const,
  streams: (id: UUID) => ["sessions", id, "streams"] as const,
  stats: (id: UUID) => ["sessions", id, "stats"] as const,
  crew: (id: UUID) => ["sessions", id, "crew"] as const,
  photos: (id: UUID) => ["sessions", id, "photos"] as const,
  videos: (id: UUID) => ["sessions", id, "videos"] as const,
};

export const sessionsService = {
  listMine: () => api.get<Session[]>("/sessions?mine=true"),
  listForActivity: (activityId: UUID) => api.get<Session[]>(`/sessions?activity_id=${activityId}`),
  get: (id: UUID) => api.get<Session>(`/sessions/${id}`),
  update: (id: UUID, body: Partial<Session>) => api.patch<Session>(`/sessions/${id}`, body),
  remove: (id: UUID) => api.del(`/sessions/${id}`),

  streams: (id: UUID) => api.get<SessionStream[]>(`/sessions/${id}/streams`),
  stats: (id: UUID) => api.get<SessionStats>(`/sessions/${id}/stats`),
  analysis: (id: UUID) => api.get<Record<string, unknown>>(`/sessions/${id}/analysis`),

  crew: (id: UUID) => api.get<SessionCrew[]>(`/sessions/${id}/crew`),
  addCrew: (id: UUID, body: { user_id: UUID; sailing_role?: string }) =>
    api.post(`/sessions/${id}/crew`, body),
  removeCrew: (id: UUID, userId: UUID) => api.del(`/sessions/${id}/crew/${userId}`),

  photos: (id: UUID) => api.get<ImageRef[]>(`/sessions/${id}/photos`),
  createPhoto: (id: UUID) => api.post<ImageUploadTicket>(`/sessions/${id}/photos`),
  confirmPhoto: (id: UUID, imageId: UUID) => api.post(`/sessions/${id}/photos/${imageId}/confirm`),
  removePhoto: (id: UUID, imageId: UUID) => api.del(`/sessions/${id}/photos/${imageId}`),

  videos: (id: UUID) => api.get<FileRef[]>(`/sessions/${id}/videos`),
  createVideo: (id: UUID) => api.post<FileUploadTicket>(`/sessions/${id}/videos`),
  confirmVideo: (id: UUID, fileId: UUID) => api.post(`/sessions/${id}/videos/${fileId}/confirm`),
  removeVideo: (id: UUID, fileId: UUID) => api.del(`/sessions/${id}/videos/${fileId}`),
};
