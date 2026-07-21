import { useEffect, useRef, useState, type MutableRefObject } from "react";
import { useNavigate } from "react-router-dom";
import { Capacitor } from "@capacitor/core";

const COMMIT_THRESHOLD_PX = 60;
// Below this drag distance, direction hasn't been decided yet — lets a
// vertical scroll start normally instead of being hijacked immediately.
const DIRECTION_LOCK_PX = 10;
// Finger moves further than this without the content visually catching up as
// fast — a soft "rubber band" rather than a 1:1 follow. Shared by both the
// horizontal swipe and the vertical pull.
const RESISTANCE = 0.5;
const SLIDE_MS = 180;

export const PULL_TRIGGER_PX = 70;
const MAX_PULL_PX = 100;

// Elements that own their own touch gestures (map panning, chart interaction,
// scrollable tables/tabs, form controls, modals) — a gesture starting on one
// of these must not also drive page-navigation or pull-to-refresh.
const BAIL_SELECTOR =
  ".leaflet-container, .recharts-wrapper, .sf-tablewrap, .sf-tabs, .sf-modal__backdrop, input, textarea, select";

// document.scrollingElement.scrollTop is the authoritative "how far from the
// top" value — window.scrollY can lag or read stale during a native WebView's
// own rubber-band bounce, which would otherwise let a drag anywhere near the
// top (not just genuinely at it) start a pull.
const scrollTop = () => document.scrollingElement?.scrollTop ?? 0;

/** The app shell's single touch-gesture recognizer for the routed content
 * (attach `ref` to AppShell's `<main>`). It owns BOTH:
 *
 *  - horizontal drag → switch between the action-bar sections in `paths`
 *    (Instagram-tab style), translating the page live then sliding
 *    out/snapping back on release;
 *  - vertical drag down while already scrolled to the very top → pull-to-
 *    refresh, calling `onRefresh` past PULL_TRIGGER_PX and reporting
 *    `refreshing` so the caller can show a spinner.
 *
 * Both live in ONE non-passive `touchmove` listener on `.sf-main` on purpose.
 * On iOS/WKWebView every non-passive touchmove listener in the event path
 * forces the whole gesture onto the JS main thread; running two separate
 * recognizers (one here, one on `window`) meant the browser had to call and
 * await BOTH on every frame, which is what made scrolling stutter. With a
 * single recognizer, an ordinary vertical scroll (not at the top, or dragging
 * up) locks `"v"` and returns WITHOUT preventDefault on the very first move,
 * so it scrolls natively exactly as it did before pull-to-refresh existed.
 * Native only — no-op on web (browsers have their own overscroll refresh). */
export function useAppShellGestures<T extends HTMLElement>(
  paths: string[],
  currentPath: string,
  onRefresh: () => Promise<unknown>,
): { ref: MutableRefObject<T | null>; pull: number; refreshing: boolean } {
  const navigate = useNavigate();
  const ref = useRef<T | null>(null);
  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  // Re-read on every touchend via refs (not state) so the listeners set up
  // once in the effect below always see the latest route/path list/callback.
  const pathsRef = useRef(paths);
  pathsRef.current = paths;
  const currentPathRef = useRef(currentPath);
  currentPathRef.current = currentPath;
  const onRefreshRef = useRef(onRefresh);
  onRefreshRef.current = onRefresh;

  useEffect(() => {
    const el = ref.current;
    if (!el || !Capacitor.isNativePlatform()) return;

    let origin: { x: number; y: number } | null = null;
    // "h": horizontal swipe-nav · "pull": vertical drag-down at the top ·
    // "v": ordinary vertical scroll, left entirely to the browser.
    let locked: "h" | "pull" | "v" | null = null;
    let pullDistance = 0;
    let busy = false;

    const setTransform = (dx: number, easing: "out" | "in" | false) => {
      el.style.transition = easing ? `transform ${SLIDE_MS}ms ease-${easing}` : "none";
      el.style.transform = dx === 0 ? "" : `translateX(${dx}px)`;
    };

    const onTouchStart = (e: TouchEvent) => {
      const target = e.target as HTMLElement;
      if (target.closest(BAIL_SELECTOR)) {
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
        if (Math.abs(dx) > Math.abs(dy)) {
          locked = "h";
        } else if (dy > 0 && !busy && scrollTop() === 0) {
          // Vertical, dragging down, already at the very top → pull-to-refresh.
          locked = "pull";
        } else {
          // Any other vertical drag is a normal scroll — hand it straight to
          // the browser (no preventDefault below) so it stays on the native
          // fast path.
          locked = "v";
        }
      }
      if (locked === "h") {
        e.preventDefault();
        setTransform(dx * RESISTANCE, false);
      } else if (locked === "pull") {
        // Bail back to native scroll if the page moved off the top mid-drag.
        if (scrollTop() > 0) return;
        e.preventDefault();
        pullDistance = Math.min(dy * RESISTANCE, MAX_PULL_PX);
        setPull(pullDistance);
      }
    };

    const finishSwipe = (dx: number) => {
      const paths = pathsRef.current;
      const currentIndex = paths.findIndex((p) => currentPathRef.current.startsWith(p));
      const nextIndex = dx < 0 ? currentIndex + 1 : currentIndex - 1;
      const commit =
        Math.abs(dx) >= COMMIT_THRESHOLD_PX &&
        currentIndex !== -1 &&
        nextIndex >= 0 &&
        nextIndex < paths.length;

      if (!commit) {
        setTransform(0, "out");
        return;
      }
      const width = el.getBoundingClientRect().width;
      setTransform(dx < 0 ? -width : width, "in");
      window.setTimeout(() => {
        navigate(paths[nextIndex]);
        // New content mounts in the same wrapper — start it just off-screen
        // on the entry side, with no transition...
        setTransform(dx < 0 ? width : -width, false);
        // ...then slide it in once that off-screen position has actually been
        // painted. A single rAF isn't reliable enough on every WebView to
        // guarantee a paint happened before the next style change — the two
        // can get coalesced into one frame, which skips straight to the
        // slide-in and reads as a stray bounce. The second rAF (running in
        // the frame *after* the first, i.e. after that paint) removes the race.
        requestAnimationFrame(() => requestAnimationFrame(() => setTransform(0, "out")));
      }, SLIDE_MS);
    };

    const finishPull = () => {
      if (pullDistance >= PULL_TRIGGER_PX) {
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
      pullDistance = 0;
    };

    const onTouchEnd = (e: TouchEvent) => {
      if (!origin) return;
      const dx = e.changedTouches[0].clientX - origin.x;
      const wasLocked = locked;
      origin = null;
      locked = null;
      if (wasLocked === "h") finishSwipe(dx);
      else if (wasLocked === "pull") finishPull();
    };

    const onTouchCancel = () => {
      const wasLocked = locked;
      origin = null;
      locked = null;
      if (wasLocked === "h") setTransform(0, "out");
      else if (wasLocked === "pull") finishPull();
    };

    el.addEventListener("touchstart", onTouchStart, { passive: true });
    el.addEventListener("touchmove", onTouchMove, { passive: false });
    el.addEventListener("touchend", onTouchEnd, { passive: true });
    el.addEventListener("touchcancel", onTouchCancel, { passive: true });
    return () => {
      el.removeEventListener("touchstart", onTouchStart);
      el.removeEventListener("touchmove", onTouchMove);
      el.removeEventListener("touchend", onTouchEnd);
      el.removeEventListener("touchcancel", onTouchCancel);
    };
  }, [navigate]);

  return { ref, pull, refreshing };
}
