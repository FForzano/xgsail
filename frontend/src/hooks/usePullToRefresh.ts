import { useEffect, useRef, useState } from "react";
import { Capacitor } from "@capacitor/core";

export const PULL_TRIGGER_PX = 70;
const MAX_PULL_PX = 100;
const RESISTANCE = 0.5;
const DIRECTION_LOCK_PX = 10;

// Same rationale as useSwipeNavigation's BAIL_SELECTOR: elements that own
// their own touch gestures must not also start a pull-to-refresh drag.
const BAIL_SELECTOR =
  ".leaflet-container, .recharts-wrapper, .sf-tablewrap, .sf-tabs, .sf-modal__backdrop, input, textarea, select";

/** Social-app-style drag-down-to-refresh, native platforms only (pull-to-
 * refresh on the web would fight the browser's own overscroll behavior).
 * Only engages when the drag starts at the very top of the page's scroll;
 * past PULL_TRIGGER_PX on release it calls `onRefresh` and reports
 * `refreshing` while it's in flight, so the caller can render a spinner. */
export function usePullToRefresh(onRefresh: () => Promise<unknown>) {
  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const onRefreshRef = useRef(onRefresh);
  onRefreshRef.current = onRefresh;

  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;

    let origin: { x: number; y: number } | null = null;
    let locked: "pull" | "other" | null = null;
    let distance = 0;
    let busy = false;

    const onTouchStart = (e: TouchEvent) => {
      if (busy) return;
      const target = e.target as HTMLElement;
      if (target.closest(BAIL_SELECTOR) || window.scrollY > 0) {
        origin = null;
        return;
      }
      locked = null;
      origin = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    };

    const onTouchMove = (e: TouchEvent) => {
      if (!origin) return;
      const dx = e.touches[0].clientX - origin.x;
      const dy = e.touches[0].clientY - origin.y;
      if (!locked) {
        if (Math.abs(dx) < DIRECTION_LOCK_PX && Math.abs(dy) < DIRECTION_LOCK_PX) return;
        locked = dy > 0 && dy > Math.abs(dx) ? "pull" : "other";
      }
      if (locked !== "pull" || window.scrollY > 0) return;
      e.preventDefault();
      distance = Math.min(dy * RESISTANCE, MAX_PULL_PX);
      setPull(distance);
    };

    const finish = () => {
      const wasPulling = locked === "pull";
      origin = null;
      locked = null;
      if (!wasPulling) return;
      if (distance >= PULL_TRIGGER_PX) {
        busy = true;
        setPull(PULL_TRIGGER_PX);
        setRefreshing(true);
        onRefreshRef.current().finally(() => {
          busy = false;
          setRefreshing(false);
          setPull(0);
        });
      } else {
        setPull(0);
      }
      distance = 0;
    };

    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: false });
    window.addEventListener("touchend", finish, { passive: true });
    window.addEventListener("touchcancel", finish, { passive: true });
    return () => {
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", finish);
      window.removeEventListener("touchcancel", finish);
    };
  }, []);

  return { pull, refreshing };
}
