import { api } from "@/api/client";
import type {
  ImageRef,
  ImageUploadTicket,
  User,
  UserRole,
  UserSearchResult,
  UUID,
} from "@/types";

export const userKeys = {
  all: ["users"] as const,
  me: ["users", "me"] as const,
  roles: (id: UUID) => ["users", id, "roles"] as const,
  search: (q: string) => ["users", "search", q] as const,
};

export const usersService = {
  list: () => api.get<User[]>("/users"), // superadmin
  me: () => api.get<User & { profile_image: ImageRef | null }>("/users/me"),
  update: (
    id: UUID,
    changes: Partial<
      Pick<
        User,
        | "first_name"
        | "last_name"
        | "dob"
        | "unit_system"
        | "resting_hr_bpm"
        | "max_hr_bpm"
      >
    >,
  ) => api.patch<User>(`/users/${id}`, changes),
  remove: (id: UUID) => api.del(`/users/${id}`),
  search: (q: string, limit = 20) =>
    api.get<UserSearchResult[]>(`/users/search?q=${encodeURIComponent(q)}&limit=${limit}`),

  createProfileImage: () => api.post<ImageUploadTicket>("/users/me/profile-image"),
  confirmProfileImage: (imageId: UUID) =>
    api.post<{ ok: boolean; profile_image: ImageRef }>(
      `/users/me/profile-image/${imageId}/confirm`,
    ),

  roles: (id: UUID) => api.get<UserRole[]>(`/users/${id}/roles`),
};
