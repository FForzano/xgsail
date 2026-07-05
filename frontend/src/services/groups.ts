import { api } from "@/api/client";
import type { Group, GroupRole, ImageUploadTicket, UUID } from "@/types";

export const groupKeys = {
  all: ["groups"] as const,
  detail: (id: UUID) => ["groups", id] as const,
};

export const groupsService = {
  list: (mine = false) => api.get<Group[]>(`/groups${mine ? "?mine=true" : ""}`),
  get: (id: UUID) => api.get<Group>(`/groups/${id}`),
  create: (body: Partial<Group>) => api.post<Group>("/groups", body),
  update: (id: UUID, body: Partial<Group>) => api.patch<Group>(`/groups/${id}`, body),
  remove: (id: UUID) => api.del(`/groups/${id}`),

  /** Self-join on public groups lands as `requested`; manager add as `invited`. */
  addMember: (id: UUID, body: { user_id?: UUID; role?: GroupRole } = {}) =>
    api.post<{ ok: boolean; status: string }>(`/groups/${id}/members`, body),
  updateMember: (id: UUID, userId: UUID, body: { role?: GroupRole; status?: string }) =>
    api.patch(`/groups/${id}/members/${userId}`, body),
  removeMember: (id: UUID, userId: UUID) => api.del(`/groups/${id}/members/${userId}`),

  uploadImage: (id: UUID) => api.post<ImageUploadTicket>(`/groups/${id}/profile-image`),
  confirmImage: (id: UUID, imageId: UUID) =>
    api.post(`/groups/${id}/profile-image/${imageId}/confirm`),
};
