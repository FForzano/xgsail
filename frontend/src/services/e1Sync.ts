import { useEffect } from "react";
import { Capacitor } from "@capacitor/core";
import { App as CapacitorApp } from "@capacitor/app";
import type { QueryClient } from "@tanstack/react-query";
import { devicesService, deviceKeys, isE1Device } from "@/services/devices";
import { activityKeys } from "@/services/activities";
import { sessionKeys } from "@/services/sessions";
import * as nativeBle from "@/services/nativeBle";

const SYNC_INTERVAL_MS = 5 * 60 * 1000;

// Module-level, not per-hook-instance: a single sync in flight is enough,
// and this must survive AppShell re-mounting (it doesn't, but this is
// robust either way).
let syncing = false;

/** Opportunistically relays every reachable XGSail E1's buffered sessions
 * over BLE (nativeBle.uploadSessions) — this is the automatic counterpart
 * to the E1's own WiFi upload: whichever transport is available at the
 * moment gets used, with no user action either way. Silent by design (no
 * toast on success or on an unreachable device) — errors only go to the
 * console, since this runs unattended in the background of ordinary app
 * use. Safe to call repeatedly or concurrently from multiple triggers: a
 * call made while one is already in flight is a no-op, and the E1 never
 * frees a session's buffer until it receives `ack-uploaded`
 * (docs/device-protocol.md §8.4), so skipping a round loses nothing — the
 * next trigger picks it back up. */
export async function syncE1Devices(queryClient: QueryClient): Promise<void> {
  if (!Capacitor.isNativePlatform() || syncing) return;
  syncing = true;
  try {
    const [types, devices] = await Promise.all([devicesService.listTypes(), devicesService.list()]);
    const e1Devices = devices.filter((d) => isE1Device(d, types));

    let anyUploaded = false;
    for (const device of e1Devices) {
      if (!device.external_id) continue;
      const key = await nativeBle.getStoredDeviceKey(device.id);
      if (!key) continue; // never claimed from this phone — nothing to relay with
      try {
        const scanned = await nativeBle.findByExternalId(device.external_id);
        if (!scanned) continue; // not currently in range — retried on the next trigger
        const results = await nativeBle.uploadSessions(scanned, device.id);
        if (results.some((r) => r.uploaded)) anyUploaded = true;
      } catch (err) {
        console.error(`[e1Sync] relay failed for device ${device.id}`, err);
      }
    }

    if (anyUploaded) {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: deviceKeys.all }),
        queryClient.invalidateQueries({ queryKey: activityKeys.all }),
        queryClient.invalidateQueries({ queryKey: sessionKeys.mine }),
      ]);
    }
  } finally {
    syncing = false;
  }
}

/** Wires syncE1Devices to app start, foreground resume, and a periodic
 * fallback — mounted once from AppShell. No user-facing UI: E1 upload
 * relay is meant to require no user action at all (unlike the phone's own
 * recordings in RegistraPage, which do surface upload status). iOS/Android
 * don't allow a reliable BLE scan with the app fully closed, so this is
 * necessarily opportunistic — foreground/recent-background only; nothing
 * is lost meanwhile since the device keeps its buffer until acknowledged. */
export function useE1AutoSync(queryClient: QueryClient): void {
  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;
    void syncE1Devices(queryClient);

    const listenerPromise = CapacitorApp.addListener("appStateChange", ({ isActive }) => {
      if (isActive) void syncE1Devices(queryClient);
    });
    const interval = window.setInterval(() => void syncE1Devices(queryClient), SYNC_INTERVAL_MS);

    return () => {
      void listenerPromise.then((h) => h.remove());
      window.clearInterval(interval);
    };
  }, [queryClient]);
}
