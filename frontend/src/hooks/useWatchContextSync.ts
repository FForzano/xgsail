import { useEffect } from "react";
import { Capacitor } from "@capacitor/core";
import { App as CapacitorApp } from "@capacitor/app";
import * as nativeWatch from "@/services/nativeWatch";

const RESYNC_MS = 10 * 60_000;

/** Keeps the paired Apple Watch's context fresh — boat, claim state and a
 * live wind snapshot — on app start, every foreground and every few minutes
 * while open, so a sailor who glances at the phone before casting off leaves
 * with a current wind on the wrist. The watch persists whatever it last got
 * and sails without it. Mounted once from AppShell next to `useWatchRelay`;
 * no-op off native, signed out, or while navigation mode suspends the
 * shell's background services. */
export function useWatchContextSync(userId: string | undefined, enabled = true): void {
  useEffect(() => {
    if (!Capacitor.isNativePlatform() || !userId || !enabled) return;
    const sync = () => void nativeWatch.syncContext().catch(() => {});

    sync();
    const timer = window.setInterval(sync, RESYNC_MS);
    const appListener = CapacitorApp.addListener("appStateChange", ({ isActive }) => {
      if (isActive) sync();
    });
    return () => {
      window.clearInterval(timer);
      void appListener.then((h) => h.remove());
    };
  }, [userId, enabled]);
}
