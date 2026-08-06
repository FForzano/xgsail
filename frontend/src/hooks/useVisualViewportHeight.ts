import { useEffect } from "react";

// visualViewport (not @capacitor/keyboard) so the fix ships via OTA — native
// plugin changes can't, per docs/ota-updates.md.
export function useVisualViewportHeight() {
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;

    const setHeight = () => {
      document.documentElement.style.setProperty("--sf-vvh", `${vv.height}px`);
    };

    setHeight();
    vv.addEventListener("resize", setHeight);
    vv.addEventListener("scroll", setHeight);

    return () => {
      vv.removeEventListener("resize", setHeight);
      vv.removeEventListener("scroll", setHeight);
    };
  }, []);
}
