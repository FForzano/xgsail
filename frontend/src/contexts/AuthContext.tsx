import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, AUTH_EXPIRED_EVENT } from "@/api/client";
import { authService } from "@/services/auth";
import type { Capabilities, User } from "@/types";

export type AuthStatus = "loading" | "authed" | "anon";

export interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  caps: Capabilities | null;
  login: (email: string, password: string) => Promise<void>;
  register: (body: {
    email: string;
    password: string;
    first_name?: string;
    last_name?: string;
    terms_and_conditions: boolean;
  }) => Promise<void>;
  logout: () => Promise<void>;
  /** Re-fetch capabilities after membership/role-changing mutations. */
  refreshCaps: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const queryClient = useQueryClient();

  const loadIdentity = useCallback(async () => {
    try {
      const c = await authService.capabilities();
      setCaps(c);
      setStatus("authed");
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
        setCaps(null);
        setStatus("anon");
      } else {
        // Network/server error: stay anon but don't wipe a valid session's
        // cookie state — a reload retries.
        setCaps(null);
        setStatus("anon");
      }
    }
  }, []);

  useEffect(() => {
    void loadIdentity();
  }, [loadIdentity]);

  // The api client dispatches this when a refresh attempt fails.
  useEffect(() => {
    const onExpired = () => {
      setCaps(null);
      setStatus("anon");
      queryClient.clear();
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, [queryClient]);

  const login = useCallback(
    async (email: string, password: string) => {
      await authService.login(email, password);
      await loadIdentity();
    },
    [loadIdentity],
  );

  const register = useCallback(
    async (body: Parameters<AuthContextValue["register"]>[0]) => {
      await authService.register(body);
      await login(body.email, body.password);
    },
    [login],
  );

  const logout = useCallback(async () => {
    try {
      await authService.logout();
    } finally {
      setCaps(null);
      setStatus("anon");
      queryClient.clear();
    }
  }, [queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user: caps?.user ?? null,
      caps,
      login,
      register,
      logout,
      refreshCaps: loadIdentity,
    }),
    [status, caps, login, register, logout, loadIdentity],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
