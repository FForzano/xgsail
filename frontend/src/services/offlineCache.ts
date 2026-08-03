/** Tiny localStorage read/write helper for offline fallbacks (e.g. the boat
 * picker in airplane mode). Never throws — a broken cache must never break
 * the app, so callers can use it unconditionally as a last resort. */
const NS = "sf_";

export function readCache<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(NS + key);
    if (raw === null) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function writeCache<T>(key: string, value: T): void {
  try {
    localStorage.setItem(NS + key, JSON.stringify(value));
  } catch {
    // Quota exceeded or storage disabled — silently skip, caller already
    // has the fresh data in memory.
  }
}

export function removeCache(key: string): void {
  try {
    localStorage.removeItem(NS + key);
  } catch {
    // ignore
  }
}
