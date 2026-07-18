import { useCallback, useSyncExternalStore } from "react";
import { Capacitor, registerPlugin } from "@capacitor/core";
import { Directory, Encoding, Filesystem } from "@capacitor/filesystem";
import { LocalNotifications } from "@capacitor/local-notifications";
import { BatteryOptimization } from "@capawesome-team/capacitor-android-battery-optimization";
import type { UUID } from "@/types";

// Native-only: records a GPS track while the app is backgrounded/the phone
// is locked, using @capacitor-community/background-geolocation (the only
// plugin in this stack that can run a foreground service + persistent
// notification on Android — @capacitor/geolocation cannot). No-ops on web,
// same convention as nativeAuth.ts/nativeUpdater.ts.
//
// Points are appended to a raw newline-delimited log as they arrive (cheap,
// no re-serialization of a growing XML document per fix) and only turned
// into real GPX XML once, when the recording is stopped — see `finalize()`.
// The finished .gpx is then handed to the existing `/api/imports` pipeline
// unchanged (see useImportUpload / RegistraPage), so the backend needs no
// awareness that this GPX came from a phone recording instead of a picked
// file or another app's share.

interface BackgroundGeolocationPlugin {
  addWatcher(
    options: {
      backgroundTitle: string;
      backgroundMessage: string;
      requestPermissions: boolean;
      stale: boolean;
      distanceFilter: number;
    },
    callback: (
      location: { latitude: number; longitude: number; time: number } | null,
      error?: { message: string; code?: string },
    ) => void,
  ): Promise<string>;
  removeWatcher(options: { id: string }): Promise<void>;
  openSettings(): Promise<void>;
}

const BackgroundGeolocation = Capacitor.isNativePlatform()
  ? registerPlugin<BackgroundGeolocationPlugin>("BackgroundGeolocation")
  : null;

// Sentinel `error` values set on a recording when the plugin's watcher
// rejects with its "NOT_AUTHORIZED" code — RegistraPage maps these to a
// translated message (+ an "open settings" action for the permission case),
// rather than showing the plugin's raw (English-only) error text. Android
// distinguishes the two cases in the rejection message; iOS reports both as
// "Permission denied." (CoreLocation collapses "services off" into the same
// `.denied` authorization status), so on iOS a disabled Location Services
// toggle also surfaces as ERROR_PERMISSION_DENIED.
export const ERROR_PERMISSION_DENIED = "LOCATION_PERMISSION_DENIED";
export const ERROR_LOCATION_SERVICES_DISABLED = "LOCATION_SERVICES_DISABLED";

export async function openSettings(): Promise<void> {
  if (!BackgroundGeolocation) return;
  await BackgroundGeolocation.openSettings();
}

export type RecordingStatus =
  | "recording"
  | "paused"
  | "stopped"
  | "uploading"
  | "uploaded"
  | "failed"
  | "permission_error";

export interface RecordingMeta {
  id: UUID;
  boatId: UUID;
  activityId: UUID | null; // null = standalone ("uscita singola")
  startedAt: string;
  endedAt: string | null;
  status: RecordingStatus;
  pointCount: number;
  sessionId?: UUID; // set once uploaded
  error?: string; // set when status is "failed", so a retry isn't required just to see why
}

// A fix is only persisted at most once per this interval — the plugin can
// deliver updates faster than this (foreground-service GPS chips typically
// can't be told "only wake up once a minute"), so the once-a-minute sampling
// requirement is enforced here rather than relying on plugin-level timing.
const SAMPLE_INTERVAL_MS = 60_000;

const INDEX_PATH = "recordings/index.json";
const rawPath = (id: string) => `recordings/${id}.ndjson`;
const gpxPath = (id: string) => `recordings/${id}.gpx`;

let index: RecordingMeta[] = [];
let indexLoaded = false;
let active: { id: UUID; watcherId: string | null; lastSampleAt: number } | null = null;
const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((l) => l());
}

async function ensureDir() {
  try {
    await Filesystem.mkdir({ path: "recordings", directory: Directory.Data });
  } catch {
    // already exists
  }
}

async function loadIndex(): Promise<RecordingMeta[]> {
  if (indexLoaded) return index;
  await ensureDir();
  try {
    const { data } = await Filesystem.readFile({
      path: INDEX_PATH,
      directory: Directory.Data,
      encoding: Encoding.UTF8,
    });
    index = JSON.parse(data as string);
  } catch {
    index = [];
  }
  indexLoaded = true;
  return index;
}

async function saveIndex() {
  // New array reference so useSyncExternalStore's Object.is check (compared
  // against the snapshot it cached from the last notify) actually detects
  // the change — entries are mutated in place above, which wouldn't move
  // the array reference on its own.
  index = [...index];
  await ensureDir();
  await Filesystem.writeFile({
    path: INDEX_PATH,
    directory: Directory.Data,
    encoding: Encoding.UTF8,
    data: JSON.stringify(index),
  });
  notify();
}

async function appendPoint(id: UUID, lat: number, lon: number, isoTime: string) {
  const line = `${JSON.stringify({ lat, lon, t: isoTime })}\n`;
  try {
    await Filesystem.appendFile({ path: rawPath(id), directory: Directory.Data, encoding: Encoding.UTF8, data: line });
  } catch {
    // First write for this recording — appendFile requires the file to exist
    // on some platforms, so fall back to a plain write.
    await Filesystem.writeFile({ path: rawPath(id), directory: Directory.Data, encoding: Encoding.UTF8, data: line });
  }
}

function toGpx(points: { lat: number; lon: number; t: string }[]): string {
  const trkpts = points
    .map((p) => `<trkpt lat="${p.lat}" lon="${p.lon}"><time>${p.t}</time></trkpt>`)
    .join("");
  return (
    `<?xml version="1.0" encoding="UTF-8"?>` +
    `<gpx version="1.1" creator="XGSail"><trk><trkseg>${trkpts}</trkseg></trk></gpx>`
  );
}

async function finalize(id: UUID): Promise<void> {
  const { data } = await Filesystem.readFile({ path: rawPath(id), directory: Directory.Data, encoding: Encoding.UTF8 });
  const points = (data as string)
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as { lat: number; lon: number; t: string });
  await Filesystem.writeFile({
    path: gpxPath(id),
    directory: Directory.Data,
    encoding: Encoding.UTF8,
    data: toGpx(points),
  });
}

/** Reads a finished recording's GPX bytes as a `File`, ready for the same
 * upload pipeline a picked/shared GPX file goes through — same
 * base64-or-Blob handling as useShareTarget.ts's `toFile()`. */
export async function readRecordingGpx(id: UUID): Promise<File> {
  const { data } = await Filesystem.readFile({ path: gpxPath(id), directory: Directory.Data });
  const blob =
    typeof data === "string"
      ? await (await fetch(`data:application/gpx+xml;base64,${data}`)).blob()
      : data;
  return new File([blob], `registrazione-${id}.gpx`, { type: "application/gpx+xml" });
}

function onWatcherLocation(id: UUID, location: { latitude: number; longitude: number; time: number }) {
  if (!active || active.id !== id) return;
  const now = Date.now();
  if (now - active.lastSampleAt < SAMPLE_INTERVAL_MS) return;
  active.lastSampleAt = now;
  const isoTime = new Date(location.time).toISOString();
  void appendPoint(id, location.latitude, location.longitude, isoTime).then(async () => {
    const entry = index.find((r) => r.id === id);
    if (entry) {
      entry.pointCount += 1;
      await saveIndex();
    }
  });
}

function onWatcherError(id: UUID, error: { message: string; code?: string }) {
  // The plugin never grants a watcher a second chance after this — it
  // stops delivering updates for it, so the recording can't continue.
  // Surface it as a failure instead of leaving the UI stuck showing
  // "recording" with no points ever arriving.
  if (error.code !== "NOT_AUTHORIZED" || !active || active.id !== id) return;
  const entry = index.find((r) => r.id === id);
  if (entry) {
    // Not "failed": that status is reused by the upload-retry loop in
    // RegistraPage, which would silently overwrite this message with a
    // "file not found" error the next time it runs (finalize() — which
    // writes the .gpx — was never reached, since stop() was never called).
    entry.status = "permission_error";
    entry.error = error.message.toLowerCase().includes("disabled")
      ? ERROR_LOCATION_SERVICES_DISABLED
      : ERROR_PERMISSION_DENIED;
  }
  active = null;
  void saveIndex();
}

/** Starts (or restarts, on resume) the plugin's watcher for `id` — points
 * keep appending to that same recording's raw log regardless of how many
 * watcher start/stop cycles a pause/resume sequence goes through. */
async function addWatcherFor(id: UUID): Promise<string> {
  if (!BackgroundGeolocation) throw new Error("Not available on web");
  return BackgroundGeolocation.addWatcher(
    {
      backgroundTitle: "XGSail",
      backgroundMessage: "Registrazione GPS in corso",
      requestPermissions: true,
      stale: false,
      distanceFilter: 0,
    },
    (location, error) => {
      if (error) {
        onWatcherError(id, error);
        return;
      }
      if (location) onWatcherLocation(id, location);
    },
  );
}

// Cap on how long `start()` waits to confirm GPS is actually usable before
// writing anything to disk — the plugin reports a permission/location-
// services failure quickly (it's a static OS check, not a fix), but a
// granted permission with a slow-to-arrive fix (e.g. indoors) shouldn't
// block starting the recording forever, so past this we proceed optimistically.
const GPS_CHECK_TIMEOUT_MS = 8_000;

export async function start(boatId: UUID, activityId: UUID | null): Promise<UUID> {
  if (!BackgroundGeolocation) throw new Error("Not available on web");
  if (active) throw new Error("A recording is already in progress");

  // Android 13+ won't show the plugin's foreground-service notification
  // unless this is explicitly granted at runtime — the plugin only
  // declares the permission in its manifest, it never requests it itself.
  await LocalNotifications.requestPermissions();

  // Doze/App Standby can otherwise pause GPS updates once the screen locks.
  // This only covers the standard Android exemption — some OEMs (Xiaomi,
  // Huawei, Samsung, Oppo/Vivo/OnePlus, ...) layer their own battery
  // manager on top that no standard API can request; RegistraPage shows a
  // static hint about that, since it can't be detected/handled here.
  if (Capacitor.getPlatform() === "android") {
    const { enabled } = await BatteryOptimization.isBatteryOptimizationEnabled();
    if (enabled) await BatteryOptimization.requestIgnoreBatteryOptimization();
  }

  const id = crypto.randomUUID() as UUID;

  // Confirm GPS is actually usable *before* creating any local recording
  // data (index entry + files) — the watcher's callback only reports
  // NOT_AUTHORIZED asynchronously, well after addWatcher's own promise
  // resolves, so `active` is deliberately left unset until that first
  // callback result (or the timeout above) comes in; onWatcherLocation/
  // onWatcherError both no-op while `active` is unset, so this first
  // result is only used to decide whether to proceed, not recorded as data.
  let earlyError: { message: string; code?: string } | null = null;
  let resolveFirstResult: (() => void) | null = null;
  const firstResult = new Promise<void>((resolve) => {
    resolveFirstResult = resolve;
  });

  const watcherId = await BackgroundGeolocation.addWatcher(
    {
      backgroundTitle: "XGSail",
      backgroundMessage: "Registrazione GPS in corso",
      requestPermissions: true,
      stale: false,
      distanceFilter: 0,
    },
    (location, error) => {
      if (resolveFirstResult) {
        if (error) earlyError = error;
        const resolve = resolveFirstResult;
        resolveFirstResult = null;
        resolve();
      }
      if (error) {
        onWatcherError(id, error);
        return;
      }
      if (location) onWatcherLocation(id, location);
    },
  );

  await Promise.race([firstResult, new Promise<void>((resolve) => setTimeout(resolve, GPS_CHECK_TIMEOUT_MS))]);
  resolveFirstResult = null;

  // Copied to a local so TS narrows this read normally — `earlyError` itself
  // is reassigned from inside the addWatcher callback above, so TS can't
  // narrow it directly at this point.
  const failure = earlyError as { message: string; code?: string } | null;
  if (failure && failure.code === "NOT_AUTHORIZED") {
    try {
      await BackgroundGeolocation.removeWatcher({ id: watcherId });
    } catch {
      // plugin already stopped delivering updates for this watcher
    }
    const message = failure.message.toLowerCase().includes("disabled")
      ? ERROR_LOCATION_SERVICES_DISABLED
      : ERROR_PERMISSION_DENIED;
    throw new Error(message);
  }

  await loadIndex();
  index.push({
    id,
    boatId,
    activityId,
    startedAt: new Date().toISOString(),
    endedAt: null,
    status: "recording",
    pointCount: 0,
  });
  await saveIndex();

  active = { id, watcherId, lastSampleAt: 0 };
  notify();
  return id;
}

/** Stops GPS updates (and the foreground notification) without finalizing
 * the recording — the raw point log stays open so `resume()` can keep
 * appending to the same track. */
export async function pause(): Promise<void> {
  if (!BackgroundGeolocation || !active || !active.watcherId) return;
  await BackgroundGeolocation.removeWatcher({ id: active.watcherId });
  active.watcherId = null;
  const entry = index.find((r) => r.id === active!.id);
  if (entry) entry.status = "paused";
  await saveIndex();
}

export async function resume(): Promise<void> {
  if (!active || active.watcherId) return;
  const watcherId = await addWatcherFor(active.id);
  active.watcherId = watcherId;
  const entry = index.find((r) => r.id === active!.id);
  if (entry) entry.status = "recording";
  await saveIndex();
}

export async function stop(): Promise<void> {
  if (!BackgroundGeolocation || !active) return;
  const { id, watcherId } = active;
  if (watcherId) await BackgroundGeolocation.removeWatcher({ id: watcherId });
  active = null;
  await finalize(id);
  const entry = index.find((r) => r.id === id);
  if (entry) {
    entry.status = "stopped";
    entry.endedAt = new Date().toISOString();
  }
  await saveIndex();
}

export async function list(): Promise<RecordingMeta[]> {
  return [...(await loadIndex())].sort((a, b) => b.startedAt.localeCompare(a.startedAt));
}

export async function setStatus(
  id: UUID,
  status: RecordingStatus,
  sessionId?: UUID,
  error?: string,
): Promise<void> {
  await loadIndex();
  const entry = index.find((r) => r.id === id);
  if (!entry) return;
  entry.status = status;
  if (sessionId) entry.sessionId = sessionId;
  entry.error = status === "failed" ? error : undefined;
  await saveIndex();
}

export async function setActivity(id: UUID, activityId: UUID | null): Promise<void> {
  await loadIndex();
  const entry = index.find((r) => r.id === id);
  if (!entry) return;
  entry.activityId = activityId;
  await saveIndex();
}

export async function remove(id: UUID): Promise<void> {
  await loadIndex();
  index = index.filter((r) => r.id !== id);
  await saveIndex();
  for (const path of [rawPath(id), gpxPath(id)]) {
    try {
      await Filesystem.deleteFile({ path, directory: Directory.Data });
    } catch {
      // already gone
    }
  }
}

export function activeRecordingId(): UUID | null {
  return active?.id ?? null;
}

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

/** Live list of local recordings, re-rendering whenever the index changes
 * (start/stop/upload/delete/reassign). Always empty on web. */
export function useRecordings(): { recordings: RecordingMeta[]; refresh: () => void } {
  const snapshot = useSyncExternalStore(subscribe, () => index);
  const refresh = useCallback(() => {
    void loadIndex().then(notify);
  }, []);
  return { recordings: Capacitor.isNativePlatform() ? snapshot : [], refresh };
}
