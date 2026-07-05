import { api } from "@/api/client";
import type {
  Boat,
  BoatClass,
  BoatMember,
  BoatRole,
  FileUploadTicket,
  ImageUploadTicket,
  UUID,
} from "@/types";

export const boatKeys = {
  all: ["boats"] as const,
  mine: ["boats", "mine"] as const,
  detail: (id: UUID) => ["boats", id] as const,
  members: (id: UUID) => ["boats", id, "members"] as const,
  classes: ["boat-classes"] as const,
};

export const boatsService = {
  list: (mine = false) => api.get<Boat[]>(`/boats${mine ? "?mine=true" : ""}`),
  get: (id: UUID) => api.get<Boat>(`/boats/${id}`),
  create: (body: Partial<Boat>) => api.post<Boat>("/boats", body),
  update: (id: UUID, body: Partial<Boat>) => api.patch<Boat>(`/boats/${id}`, body),
  remove: (id: UUID) => api.del(`/boats/${id}`),

  members: (id: UUID) => api.get<BoatMember[]>(`/boats/${id}/members`),
  addMember: (id: UUID, body: { user_id: UUID; role?: BoatRole; default_sailing_role?: string }) =>
    api.post(`/boats/${id}/members`, body),
  setMemberRole: (id: UUID, userId: UUID, role: BoatRole) =>
    api.patch(`/boats/${id}/members/${userId}`, { role }),
  removeMember: (id: UUID, userId: UUID) => api.del(`/boats/${id}/members/${userId}`),

  createPhoto: (id: UUID) => api.post<ImageUploadTicket>(`/boats/${id}/photos`),
  confirmPhoto: (id: UUID, imageId: UUID) => api.post(`/boats/${id}/photos/${imageId}/confirm`),
  removePhoto: (id: UUID, imageId: UUID) => api.del(`/boats/${id}/photos/${imageId}`),
  uploadCert: (id: UUID) => api.post<FileUploadTicket>(`/boats/${id}/cert`),
  uploadMbsa: (id: UUID) => api.post<FileUploadTicket>(`/boats/${id}/mbsa`),

  listClasses: () => api.get<BoatClass[]>("/boat-classes"),
  createClass: (body: Partial<BoatClass>) => api.post<BoatClass>("/boat-classes", body),
  updateClass: (id: UUID, body: Partial<BoatClass>) =>
    api.patch<BoatClass>(`/boat-classes/${id}`, body),
  removeClass: (id: UUID) => api.del(`/boat-classes/${id}`),
};
