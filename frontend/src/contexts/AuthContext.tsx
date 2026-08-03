import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Capacitor } from "@capacitor/core";
import { Network } from "@capacitor/network";
import { ApiError, AUTH_EXPIRED_EVENT, setAccessToken } from "@/api/client";
import { authService } from "@/services/auth";
import { readCache, removeCache, writeCache } from "@/services/offlineCache";
import type { Capabilities, User } from "@/types";

// Last known-good capabilities, so a native cold start with no connectivity can
// render the authenticated app instead of bouncing to a login page that itself
// needs the network. Capabilities carry no secret: the refresh token stays in
// Keychain/Keystore (services/nativeAuth.ts) and the access token in memory
// (api/client.ts) — neither is ever written here.
const CAPS_CACHE_KEY = "caps_cache";

// Dynamic import: keeps @aparajita/capacitor-secure-storage out of the web
// bundle entirely (see services/nativeAuth.ts) — this module is only ever
// touched when actually running inside the native shell.
const nativeAuth = () => import("@/services/nativeAuth");

/** A persisted native refresh token is what makes an unverified cached
 * identity legitimate: the session can still be re-established once the
 * network is back. Web has no JS-visible refresh token, so it never
 * reconstructs a session from cache. */
async function hasNativeSession(): Promise<boolean> {
  if (!Capacitor.isNativePlatform()) return false;
  return (await nativeAuth()).getNativeRefreshToken() !== null;
}

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
    privacy_policy: boolean;
  }) => Promise<void>;
  logout: () => Promise<void>;
  /** True when `caps` come from the offline snapshot and have not been
   * confirmed by the server yet (native cold start with no connectivity). */
  identityStale: boolean;
  /** Re-fetch capabilities after membership/role-changing mutations. */
  refreshCaps: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [identityStale, setIdentityStale] = useState(false);
  const queryClient = useQueryClient();

  const loadIdentity = useCallback(async () => {
    try {
      const c = await authService.capabilities();
      setCaps(c);
      setStatus("authed");
      setIdentityStale(false);
      writeCache(CAPS_CACHE_KEY, c);
      return;
    } catch (e) {
      // Same distinction api/client.ts draws for refresh: an ApiError means
      // the server judged the request, anything else (a fetch TypeError)
      // means it never got a response. Only the former can be a logout.
      if (!(e instanceof ApiError) && (await hasNativeSession())) {
        const cached = readCache<Capabilities>(CAPS_CACHE_KEY);
        if (cached) {
          setCaps(cached);
          setStatus("authed");
          setIdentityStale(true);
          return;
        }
      }
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
        removeCache(CAPS_CACHE_KEY);
      }
      setCaps(null);
      setStatus("anon");
      setIdentityStale(false);
    }
  }, []);

  useEffect(() => {
    // Loads the persisted native refresh token (if any) before the first
    // capabilities call, so a returning native user doesn't have to log in
    // again — a no-op on web.
    const init = Capacitor.isNativePlatform()
      ? nativeAuth().then((m) => m.initNativeAuth())
      : Promise.resolve();
    void init.then(loadIdentity);
  }, [loadIdentity]);

  // A cached identity is unverified, so re-check it as soon as there is a
  // network again rather than waiting for the next app launch.
  useEffect(() => {
    if (!identityStale || !Capacitor.isNativePlatform()) return;
    const sub = Network.addListener("networkStatusChange", (s) => {
      if (s.connected) void loadIdentity();
    });
    return () => void sub.then((h) => h.remove());
  }, [identityStale, loadIdentity]);

  // The api client dispatches this when a refresh attempt fails.
  useEffect(() => {
    const onExpired = () => {
      setAccessToken(null);
      removeCache(CAPS_CACHE_KEY);
      setCaps(null);
      setStatus("anon");
      setIdentityStale(false);
      queryClient.clear();
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, [queryClient]);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await authService.login(email, password);
      if (Capacitor.isNativePlatform()) {
        await (await nativeAuth()).persistNativeLogin(res);
      }
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
      if (Capacitor.isNativePlatform()) {
        const m = await nativeAuth();
        await authService.logout(m.getNativeRefreshToken() ?? undefined);
        await m.clearNativeAuth();
      } else {
        await authService.logout();
      }
    } finally {
      setAccessToken(null);
      removeCache(CAPS_CACHE_KEY);
      setCaps(null);
      setStatus("anon");
      setIdentityStale(false);
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
      identityStale,
      refreshCaps: loadIdentity,
    }),
    [status, caps, identityStale, login, register, logout, loadIdentity],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
