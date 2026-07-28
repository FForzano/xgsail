import { useEffect, useState } from "react";

const secondsUntil = (target: string, clamp: boolean): number => {
  const delta = Math.floor((Date.parse(target) - Date.now()) / 1000);
  return clamp ? Math.max(0, delta) : delta;
};

/** Seconds between now and `target` (ISO timestamp), ticking every second.
 * With `clamp` the value stops at 0 once the target passes; without it it
 * keeps going negative — see the two wrappers below. */
function useTargetDelta(target: string | null, clamp: boolean): number {
  const [remaining, setRemaining] = useState(() => (target ? secondsUntil(target, clamp) : 0));

  useEffect(() => {
    if (!target) return;
    const tick = () => setRemaining(secondsUntil(target, clamp));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [target, clamp]);

  return remaining;
}

/** Seconds remaining until `expiresAt` (ISO timestamp), ticking every second.
 * Never goes below 0 — an expired deadline is just "0 left". */
export function useCountdown(expiresAt: string | null): number {
  return useTargetDelta(expiresAt, true);
}

/** Same, but keeps counting past the target as a negative value — for a race
 * start timer, where "1:23 since the gun" matters as much as the countdown to
 * it (see components/registra/NavStartTimer.tsx). */
export function useSignedCountdown(startsAt: string | null): number {
  return useTargetDelta(startsAt, false);
}

/** `m:ss`, with an explicit `+` once the target has passed — only reachable
 * via useSignedCountdown, since useCountdown clamps at 0. */
export function fmtCountdown(sec: number): string {
  const sign = sec < 0 ? "+" : "";
  const abs = Math.abs(sec);
  const m = Math.floor(abs / 60);
  const s = abs % 60;
  return `${sign}${m}:${s.toString().padStart(2, "0")}`;
}
