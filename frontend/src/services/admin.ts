import { api } from "@/api/client";
import type {
  Activity,
  AdminAccessLogEntry,
  AdminSessionSummary,
  AdminUserDetail,
  Boat,
  UUID,
} from "@/types";

export const adminKeys = {
  userDetail: (id: UUID) => ["admin", "users", id] as const,
  userBoats: (id: UUID) => ["admin", "users", id, "boats"] as const,
  userActivities: (id: UUID, limit: number, offset: number) =>
    ["admin", "users", id, "activities", limit, offset] as const,
  userSessions: (id: UUID, limit: number, offset: number) =>
    ["admin", "users", id, "sessions", limit, offset] as const,
  accessLog: (targetUserId: UUID, limit: number, offset: number) =>
    ["admin", "access-log", targetUserId, limit, offset] as const,
};

export const adminService = {
  userDetail: (id: UUID) => api.get<AdminUserDetail>(`/admin/users/${id}`),
  userBoats: (id: UUID) => api.get<Boat[]>(`/admin/users/${id}/boats`),
  userActivities: (id: UUID, limit: number, offset: number) =>
    api.get<Activity[]>(`/admin/users/${id}/activities?limit=${limit}&offset=${offset}`),
  userSessions: (id: UUID, limit: number, offset: number) =>
    api.get<AdminSessionSummary[]>(`/admin/users/${id}/sessions?limit=${limit}&offset=${offset}`),
  accessLog: (targetUserId: UUID, limit: number, offset: number) =>
    api.get<AdminAccessLogEntry[]>(
      `/admin/access-log?target_user_id=${targetUserId}&limit=${limit}&offset=${offset}`,
    ),
};
