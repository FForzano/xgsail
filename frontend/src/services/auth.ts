import { api, setAccessToken } from "@/api/client";
import type { Capabilities, MyMemberships, User } from "@/types";

/** Shape of /auth/login and /auth/refresh responses. `refresh_token` exists
 * for native clients (persisted into secure storage by `services/nativeAuth`)
 * — the web app must never read or store it, only the in-memory access token
 * set below. */
export interface LoginResponse {
  user: User;
  csrf_token: string;
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

export const authService = {
  register: (body: {
    email: string;
    password: string;
    first_name?: string;
    last_name?: string;
    terms_and_conditions: boolean;
    privacy_policy: boolean;
  }) => api.post<User>("/auth/register", body),

  login: async (email: string, password: string) => {
    const res = await api.post<LoginResponse>("/auth/login", { email, password });
    setAccessToken(res.access_token);
    return res;
  },

  /** `refreshToken` is native-only (see services/nativeAuth) — web relies on
   * the httpOnly cookie instead and omits it. */
  logout: (refreshToken?: string) =>
    api.post("/auth/logout", refreshToken ? { refresh_token: refreshToken } : undefined),

  /** Identity + roles/permissions/memberships in one call (embeds `user`). */
  capabilities: () => api.get<Capabilities>("/auth/capabilities"),

  changePassword: (current_password: string, new_password: string) =>
    api.post("/auth/change-password", { current_password, new_password }),

  /** Dismiss the "Buy Me a Coffee" reminder banner, scheduling when it's
   * next eligible to show (see capabilities `support.shouldShow`). */
  dismissSupportPrompt: (donated: boolean) =>
    api.post("/auth/support-prompt", { donated }),

  myMemberships: () => api.get<MyMemberships>("/users/me/memberships"),
};
