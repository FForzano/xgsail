import { CSRF_COOKIE, CSRF_HEADER, readCookie } from "./csrf";

// Thin fetch wrapper for the SailFrames API. The access token is a JWT held
// in memory only (never localStorage, to limit XSS blast radius) and sent as
// `Authorization: Bearer` on every request — this is what makes cross-origin
// native (Capacitor) clients work, since their WebView cookie jar can't be
// relied on. The httpOnly `sf_refresh` cookie still backs the silent-refresh
// flow for web (native refreshes via its own token instead, see
// `services/nativeAuth.ts`); the CSRF header (read from the readable
// `sf_csrf` cookie) is still sent on mutations but the backend only enforces
// it for cookie-authenticated requests, so it's a no-op once Bearer is live.

// Exported for the rare case a plain browser navigation needs the API URL
// directly (e.g. a GPX file download) instead of going through `request()`.
export const BASE = import.meta.env.VITE_API_BASE ?? "/api";

// BASE's own origin when it's absolute (native: a real cross-origin host —
// there's no same-origin nginx proxy inside a WebView), empty when it's
// relative (web: same-origin "/api", nginx proxies it).
const API_ORIGIN = /^https?:\/\//.test(BASE) ? new URL(BASE).origin : "";

/** Resolve a backend-issued file URL (e.g. `storage.download_ref`'s
 * `/api/download/{key}` proxy fallback) for a direct `fetch`/`<a href>`/
 * `window.open` outside `request()`. Those URLs are relative because
 * they're built to work same-origin on web; a relative URL inside the
 * native WebView resolves against its own virtual origin
 * (`app.xgsail.com`, see `capacitor.config.ts`) instead of the real API,
 * and silently fails (wrong host, nothing there). Already-absolute URLs
 * (a real presigned S3/MinIO URL) are returned untouched. */
export function resolveApiUrl(url: string): string {
  return /^https?:\/\//.test(url) ? url : `${API_ORIGIN}${url}`;
}

// Dispatched when refresh fails — AuthContext listens and drops to anonymous.
export const AUTH_EXPIRED_EVENT = "sf:auth-expired";

// In-memory only — a hard page reload loses this and the first authenticated
// call 401s, which triggers the existing refresh-and-retry path below to
// repopulate it from the httpOnly refresh cookie (web) or stored native
// refresh token.
let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

// Native has no cookie jar to carry the refresh token, so it must send it
// explicitly in the /auth/refresh body. `services/nativeAuth.ts` registers
// this provider on native platforms only; web never sets it, so `doRefresh`
// falls back to the httpOnly cookie exactly as before.
let refreshTokenProvider: (() => string | null) | null = null;

export function setRefreshTokenProvider(fn: (() => string | null) | null): void {
  refreshTokenProvider = fn;
}

// Refresh rotates the opaque refresh token every time — native must
// re-persist the new one or the next refresh will fail (reuse detection).
// Returns a Promise the caller awaits — the persisted write must land
// before doRefresh() resolves (see the comment there): the server has
// already rotated+revoked the previous refresh token by this point, so an
// app kill before the write completes strands the device with a stale,
// now-revoked token on the next launch.
let onNativeRefreshRotated: ((refreshToken: string) => void | Promise<void>) | null = null;

export function setNativeRefreshSink(
  fn: ((refreshToken: string) => void | Promise<void>) | null,
): void {
  onNativeRefreshRotated = fn;
}

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    super(`API ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
  /** Best-effort human message from a FastAPI `{detail}` body. */
  get detail(): string {
    const b = this.body as { detail?: unknown } | null;
    if (b && typeof b.detail === "string") return b.detail;
    return this.message;
  }
}

interface RequestOptions {
  method?: string;
  /** JSON-serialised unless it's FormData (multipart, e.g. race GPX upload). */
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  /** internal: set once we have already retried after a refresh */
  _retried?: boolean;
}

// "rejected" means the server explicitly said the refresh token is no good
// (expired/revoked/reuse-detected) — that's a real logout. "network-error"
// means the fetch itself never got a response (offline, request killed by
// the OS while the app was backgrounded/locked, etc.); the refresh token
// itself was never actually judged, so it must NOT be treated as a logout
// — this request just fails and the next one gets a fresh chance to
// refresh once connectivity is back. Conflating the two used to log
// everyone out whenever a refresh attempt happened to race a phone
// lock/unlock, even though the session was perfectly valid.
type RefreshOutcome = "ok" | "rejected" | "network-error";

let refreshing: Promise<RefreshOutcome> | null = null;

// A 401 on these is expected (bad creds) or would loop the refresh itself.
const NO_REFRESH_PATHS = ["/auth/login", "/auth/register", "/auth/refresh"];

interface RefreshResponse {
  access_token: string;
  refresh_token: string;
}

async function doRefresh(): Promise<RefreshOutcome> {
  try {
    const nativeRefreshToken = refreshTokenProvider?.() ?? null;
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: nativeRefreshToken ? { "Content-Type": "application/json" } : undefined,
      body: nativeRefreshToken ? JSON.stringify({ refresh_token: nativeRefreshToken }) : undefined,
    });
    if (!res.ok) return "rejected";
    const body = (await res.json()) as RefreshResponse;
    setAccessToken(body.access_token);
    // Must be awaited: the server has already revoked the old refresh
    // token, so this write persisting the new one has to land before we
    // consider the refresh "done" — see setNativeRefreshSink's comment.
    if (nativeRefreshToken) await onNativeRefreshRotated?.(body.refresh_token);
    return "ok";
  } catch {
    return "network-error";
  }
}

async function safeJson(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export async function request<T = unknown>(
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  const method = (opts.method ?? "GET").toUpperCase();
  const isMutation = method !== "GET" && method !== "HEAD";
  const headers: Record<string, string> = { ...opts.headers };
  let body: BodyInit | undefined;
  if (opts.body instanceof FormData) {
    body = opts.body; // browser sets the multipart boundary Content-Type
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  if (isMutation) headers[CSRF_HEADER] = readCookie(CSRF_COOKIE) ?? "";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  const res = await fetch(`${BASE}${path}`, {
    method,
    credentials: "include",
    headers,
    body,
    signal: opts.signal,
  });

  if (
    res.status === 401 &&
    !opts._retried &&
    !NO_REFRESH_PATHS.some((p) => path.startsWith(p))
  ) {
    // Single-flight refresh shared across concurrent 401s, then replay once.
    const outcome = await (refreshing ??= doRefresh().finally(() => {
      refreshing = null;
    }));
    if (outcome === "ok") return request<T>(path, { ...opts, _retried: true });
    if (outcome === "rejected") window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    // "network-error": fall through and let the original 401 response
    // surface as a normal ApiError below — no logout, session untouched.
  }

  if (!res.ok) throw new ApiError(res.status, await safeJson(res));
  if (res.status === 204) return null as T;
  return (await safeJson(res)) as T;
}

export const api = {
  get: <T = unknown>(path: string, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: "GET" }),
  post: <T = unknown>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: "POST", body }),
  patch: <T = unknown>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: "PATCH", body }),
  put: <T = unknown>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: "PUT", body }),
  del: <T = unknown>(path: string, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: "DELETE" }),
};
