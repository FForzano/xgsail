// The backend sets `sf_csrf` as a JS-readable cookie (httponly=false). We echo
// it back in the `X-SF-CSRF` header on every mutation (double-submit CSRF).
export function readCookie(name: string): string | null {
  const prefix = name + "=";
  for (const part of document.cookie.split(";")) {
    const c = part.trim();
    if (c.startsWith(prefix)) return decodeURIComponent(c.slice(prefix.length));
  }
  return null;
}

export const CSRF_COOKIE = "sf_csrf";
export const CSRF_HEADER = "X-SF-CSRF";
