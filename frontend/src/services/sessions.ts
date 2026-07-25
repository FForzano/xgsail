import { api, BASE } from "@/api/client";
import type {
  FileRef,
  FileUploadTicket,
  ImageRef,
  ImageUploadTicket,
  SailingRole,
  Session,
  SessionAnalysis,
  SessionCrew,
  SessionManeuver,
  SessionStats,
  SessionStream,
  UUID,
} from "@/types";

export const sessionKeys = {
  mine: ["sessions", "mine"] as const,
  detail: (id: UUID) => ["sessions", id] as const,
  streams: (id: UUID) => ["sessions", id, "streams"] as const,
  stats: (id: UUID) => ["sessions", id, "stats"] as const,
  analysis: (id: UUID) => ["sessions", id, "analysis"] as const,
  reanalysisStatus: (id: UUID) => ["sessions", id, "reanalysis-status"] as const,
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
  // Only valid while the session is still a standalone recording (a private
  // auto-created "solo" activity wrapping just this one session) — see
  // backend/routers/sessions.py::attach_to_activity.
  attachToActivity: (id: UUID, activityId: UUID) =>
    api.post<Session>(`/sessions/${id}/attach-to-activity`, { activity_id: activityId }),
  reanalyze: (id: UUID) =>
    api.post<{ ok: boolean; session_upload_id: UUID; status: "running" }>(`/sessions/${id}/reanalyze`),
  refreshWind: (id: UUID) =>
    api.post<{ ok: boolean; session_upload_id: UUID; status: "running" }>(`/sessions/${id}/wind/refresh`),
  reanalysisStatus: (id: UUID) =>
    api.get<{ status: "running" | "failed" | null; error: string | null }>(`/sessions/${id}/reanalysis-status`),
  setTrim: (id: UUID, body: { trim_start_time: number | null; trim_end_time: number | null }) =>
    api.patch<{ ok: boolean; session_upload_id: UUID; status: "running" }>(`/sessions/${id}/trim`, body),
  updateNotes: (id: UUID, body: { notes: string | null; notes_shared: boolean }) =>
    api.patch<Session>(`/sessions/${id}/notes`, body),
  // Plain browser navigation (not `request()`) so the download prompt fires —
  // same-origin httpOnly auth cookies are sent automatically either way.
  gpxDownloadUrl: (id: UUID) => `${BASE}/sessions/${id}/gpx`,

  streams: (id: UUID) => api.get<SessionStream[]>(`/sessions/${id}/streams`),
  stats: (id: UUID) => api.get<SessionStats>(`/sessions/${id}/stats`),
  analysis: (id: UUID) => api.get<SessionAnalysis>(`/sessions/${id}/analysis`),

  correctManeuver: (id: UUID, maneuverId: UUID, maneuverType: SessionManeuver["maneuver_type"]) =>
    api.patch<SessionManeuver>(`/sessions/${id}/maneuvers/${maneuverId}`, { maneuver_type: maneuverType }),
  rejectManeuver: (id: UUID, maneuverId: UUID, rejected: boolean) =>
    api.patch<SessionManeuver>(`/sessions/${id}/maneuvers/${maneuverId}/reject`, { rejected }),
  deleteManeuver: (id: UUID, maneuverId: UUID) => api.del(`/sessions/${id}/maneuvers/${maneuverId}`),
  addManeuver: (id: UUID, body: { maneuver_type: SessionManeuver["maneuver_type"]; start_time: number; end_time: number }) =>
    api.post<{ ok: boolean; maneuver_id: UUID; status: "pending" }>(`/sessions/${id}/maneuvers`, body),

  crew: (id: UUID) => api.get<SessionCrew[]>(`/sessions/${id}/crew`),
  addCrew: (id: UUID, body: { user_id: UUID; sailing_role?: SailingRole }) =>
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
