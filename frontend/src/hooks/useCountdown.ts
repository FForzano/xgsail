import { useEffect, useState } from "react";

/** Seconds remaining until `expiresAt` (ISO timestamp), ticking every second. */
export function useCountdown(expiresAt: string | null): number {
  const [remaining, setRemaining] = useState(() =>
    expiresAt ? Math.max(0, Math.floor((Date.parse(expiresAt) - Date.now()) / 1000)) : 0,
  );

  useEffect(() => {
    if (!expiresAt) return;
    const tick = () =>
      setRemaining(Math.max(0, Math.floor((Date.parse(expiresAt) - Date.now()) / 1000)));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [expiresAt]);

  return remaining;
}

export function fmtCountdown(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}
