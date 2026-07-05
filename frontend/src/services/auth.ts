import { api } from "@/api/client";
import type { Capabilities, MyMemberships, User } from "@/types";

export const authService = {
  register: (body: {
    email: string;
    password: string;
    first_name?: string;
    last_name?: string;
    terms_and_conditions: boolean;
  }) => api.post<User>("/auth/register", body),

  login: (email: string, password: string) =>
    api.post<{ user: User; csrf_token: string }>("/auth/login", { email, password }),

  logout: () => api.post("/auth/logout"),

  /** Identity + roles/permissions/memberships in one call (embeds `user`). */
  capabilities: () => api.get<Capabilities>("/auth/capabilities"),

  changePassword: (current_password: string, new_password: string) =>
    api.post("/auth/change-password", { current_password, new_password }),

  myMemberships: () => api.get<MyMemberships>("/users/me/memberships"),
};
