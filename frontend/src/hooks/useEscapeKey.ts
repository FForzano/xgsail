import { useEffect } from "react";

/** Calls `onEscape` whenever Esc is pressed — the close-on-Esc behavior
 * shared by every full-screen overlay (Modal, ImageLightbox). */
export function useEscapeKey(onEscape: () => void): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onEscape();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onEscape]);
}
