import { useSyncExternalStore } from "react";

/** Whether a CSS media query matches, kept live as the viewport changes —
 * for the rare layout choice CSS alone can't make (rendering a different
 * component, not restyling one). */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}
