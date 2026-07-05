import { CSRF_COOKIE, CSRF_HEADER, readCookie } from "./csrf";

// Thin fetch wrapper for the SailFrames cookie-auth API. Unlike a Bearer-token
// setup there is NO token in JS: the browser holds httpOnly `sf_access` /
// `sf_refresh` cookies, we only add the CSRF header (read from the readable
// `sf_csrf` cookie) on mutations and retry once through /auth/refresh on 401.

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

// Dispatched when refresh fails — AuthContext listens and drops to anonymous.
export const AUTH_EXPIRED_EVENT = "sf:auth-expired";

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

let refreshing: Promise<boolean> | null = null;

async function doRefresh(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    return res.ok;
  } catch {
    return false;
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

  const res = await fetch(`${BASE}${path}`, {
    method,
    credentials: "include",
    headers,
    body,
    signal: opts.signal,
  });

  if (res.status === 401 && !opts._retried && !path.startsWith("/auth/")) {
    // Single-flight refresh shared across concurrent 401s, then replay once.
    const ok = await (refreshing ??= doRefresh().finally(() => {
      refreshing = null;
    }));
    if (ok) return request<T>(path, { ...opts, _retried: true });
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
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
