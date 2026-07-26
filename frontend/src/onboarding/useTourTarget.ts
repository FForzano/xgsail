import { useEffect, useState } from "react";

/** Same `data-tour` id can be tagged on two elements at once — e.g. AppShell's
 * desktop nav link and its mobile action-bar counterpart, toggled by a CSS
 * media query rather than mount/unmount — so pick whichever one is actually
 * laid out right now. */
function findVisibleTarget(dataTour: string): HTMLElement | null {
  const els = document.querySelectorAll<HTMLElement>(`[data-tour="${dataTour}"]`);
  for (const el of els) {
    if (el.getClientRects().length > 0) return el;
  }
  return null;
}

// A step's target can mount slightly after the step becomes active (e.g. a
// banner behind a query that's still loading) — a few short retries give it
// a chance before the step is given up on.
const RETRY_DELAYS_MS = [0, 150, 400, 900];

/** Resolves a step's `data-tour` target to its live bounding rect, retrying
 * briefly if it isn't in the DOM yet, and re-measuring on resize/scroll and
 * via ResizeObserver so the spotlight tracks layout changes. Calls
 * `onUnavailable` once if the target still isn't found after all retries. */
export function useTourTarget(dataTour: string, onUnavailable: () => void) {
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    let cancelled = false;
    let el: HTMLElement | null = null;
    let ro: ResizeObserver | null = null;
    const timers: ReturnType<typeof setTimeout>[] = [];

    const measure = () => {
      if (cancelled) return;
      el = findVisibleTarget(dataTour);
      setRect(el ? el.getBoundingClientRect() : null);
      if (el && !ro) {
        ro = new ResizeObserver(measure);
        ro.observe(el);
      }
    };

    RETRY_DELAYS_MS.forEach((delay) => {
      timers.push(
        setTimeout(() => {
          measure();
          if (delay === RETRY_DELAYS_MS[RETRY_DELAYS_MS.length - 1] && !el) {
            onUnavailable();
          }
        }, delay),
      );
    });

    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
      ro?.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `onUnavailable`
    // is expected to be a fresh closure each render; re-running the effect
    // for that alone would restart the retry/observer cycle pointlessly.
  }, [dataTour]);

  return rect;
}
