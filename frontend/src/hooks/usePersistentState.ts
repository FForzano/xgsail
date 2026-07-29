import { useCallback, useState } from "react";

/** `useState` whose value survives reloads in localStorage — for small UI
 * preferences that belong to the device, not the account (share-image colors,
 * map layer toggles). Anything that should follow the user across devices
 * belongs on the profile instead (see stores/unitsStore.ts). */
export function usePersistentState<T>(key: string, initial: T): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => {
    const raw = localStorage.getItem(key);
    if (raw === null) return initial;
    try {
      return JSON.parse(raw) as T;
    } catch {
      // A key written by an older build (or hand-edited) shouldn't break the
      // page — fall back to the default and let the next set() overwrite it.
      return initial;
    }
  });

  const set = useCallback(
    (next: T) => {
      setValue(next);
      localStorage.setItem(key, JSON.stringify(next));
    },
    [key],
  );

  return [value, set];
}
