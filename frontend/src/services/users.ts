import { api } from "@/api/client";
import type { ImageRef, ImageUploadTicket, User, UserRole, UserSummary, UUID } from "@/types";

export const userKeys = {
  all: ["users"] as const,
  me: ["users", "me"] as const,
  roles: (id: UUID) => ["users", id, "roles"] as const,
};

export const usersService = {
  list: () => api.get<User[]>("/users"), // superadmin
  me: () => api.get<User & { profile_image: ImageRef | null }>("/users/me"),
  update: (id: UUID, changes: Partial<Pick<User, "first_name" | "last_name" | "dob">>) =>
    api.patch<User>(`/users/${id}`, changes),
  remove: (id: UUID) => api.del(`/users/${id}`),
  lookup: (email: string) =>
    api.get<UserSummary>(`/users/lookup?email=${encodeURIComponent(email)}`),

  createProfileImage: () => api.post<ImageUploadTicket>("/users/me/profile-image"),
  confirmProfileImage: (imageId: UUID) =>
    api.post<{ ok: boolean; profile_image: ImageRef }>(
      `/users/me/profile-image/${imageId}/confirm`,
    ),

  roles: (id: UUID) => api.get<UserRole[]>(`/users/${id}/roles`),
};
