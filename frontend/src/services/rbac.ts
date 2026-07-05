import { api } from "@/api/client";
import type { Role, UserRole, UUID } from "@/types";

export const rbacService = {
  roles: () => api.get<Role[]>("/roles"),
  permissions: () => api.get<Array<{ id: UUID; key: string; description: string | null }>>(
    "/permissions",
  ),
  userRoles: (userId: UUID) => api.get<UserRole[]>(`/users/${userId}/roles`),
  grant: (body: { user_id: UUID; role_id: UUID; scope_club_id?: UUID }) =>
    api.post<UserRole>("/user-roles", body),
  revoke: (userRoleId: UUID) => api.del(`/user-roles/${userRoleId}`),
};
