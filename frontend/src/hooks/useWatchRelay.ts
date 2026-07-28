import { useEffect } from "react";
import { Capacitor } from "@capacitor/core";
import { App as CapacitorApp } from "@capacitor/app";
import type { QueryClient } from "@tanstack/react-query";
import { activityKeys } from "@/services/activities";
import { sessionKeys } from "@/services/sessions";
import { deviceKeys } from "@/services/devices";
import * as nativeWatch from "@/services/nativeWatch";
import type { UUID } from "@/types";

/** Relays sessions from the paired Apple Watch to the backend
 * (docs/device-protocol.md §9) and refreshes the affected queries. Mounted
 * once from AppShell, the counterpart to `useE1AutoSync`. It fires on three
 * triggers so nothing gets stuck on the phone: the live `watchSessionReceived`
 * event, app start, and every foreground resume — `relayPending` retries any
 * session an earlier (e.g. offline) attempt couldn't upload, deleting each
 * only after it lands. No UI of its own; no-op off native or when signed
 * out. `enabled` lets navigation mode suspend it (same rationale as
 * useE1AutoSync): the relay's file IO, uploads and query invalidations can
 * all wait until the instrument display is closed. */
export function useWatchRelay(
  queryClient: QueryClient,
  userId: UUID | undefined,
  enabled = true,
): void {
  useEffect(() => {
    if (!Capacitor.isNativePlatform() || !userId || !enabled) return;
    let unsubscribe: (() => void) | null = null;
    let cancelled = false;

    const onResult = (_event: unknown, error: Error | null) => {
      if (error) {
        console.error("[watchRelay] relay failed", error);
        return;
      }
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: deviceKeys.all }),
        queryClient.invalidateQueries({ queryKey: activityKeys.all }),
        queryClient.invalidateQueries({ queryKey: sessionKeys.mine }),
      ]);
    };

    // Retry on launch + every foreground (catches sessions that arrived while
    // offline, or an ack/upload that didn't complete last time).
    void nativeWatch.relayPending(userId, onResult);
    const appListener = CapacitorApp.addListener("appStateChange", ({ isActive }) => {
      if (isActive) void nativeWatch.relayPending(userId, onResult);
    });

    void nativeWatch.subscribe(userId, onResult).then((off) => {
      if (cancelled) off();
      else unsubscribe = off;
    });

    return () => {
      cancelled = true;
      unsubscribe?.();
      void appListener.then((h) => h.remove());
    };
  }, [queryClient, userId, enabled]);
}
