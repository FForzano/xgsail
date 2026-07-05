import { api } from "@/api/client";
import type { Club, ClubMember, ImageUploadTicket, UUID } from "@/types";

export const clubKeys = {
  all: ["clubs"] as const,
  detail: (id: UUID) => ["clubs", id] as const,
  members: (id: UUID) => ["clubs", id, "members"] as const,
};

export const clubsService = {
  list: () => api.get<Club[]>("/clubs"),
  get: (id: UUID) => api.get<Club>(`/clubs/${id}`),
  create: (body: Partial<Club>) => api.post<Club>("/clubs", body),
  update: (id: UUID, body: Partial<Club>) => api.patch<Club>(`/clubs/${id}`, body),
  deactivate: (id: UUID) => api.del(`/clubs/${id}`),

  members: (id: UUID) => api.get<ClubMember[]>(`/clubs/${id}/members`),
  /** Self-join (no user_id) lands as `requested`; manager add as `invited`. */
  addMember: (id: UUID, body: { user_id?: UUID; status?: string } = {}) =>
    api.post<{ ok: boolean; status: string }>(`/clubs/${id}/members`, body),
  setMemberStatus: (id: UUID, userId: UUID, status: string) =>
    api.patch(`/clubs/${id}/members/${userId}`, { status }),
  removeMember: (id: UUID, userId: UUID) => api.del(`/clubs/${id}/members/${userId}`),

  uploadLogo: (id: UUID) => api.post<ImageUploadTicket>(`/clubs/${id}/logo`),
  confirmLogo: (id: UUID, imageId: UUID) => api.post(`/clubs/${id}/logo/${imageId}/confirm`),
};
