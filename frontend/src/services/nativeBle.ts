import { Capacitor } from "@capacitor/core";
import { BleClient, dataViewToText, textToDataView } from "@capacitor-community/bluetooth-le";
import { SecureStorage } from "@aparajita/capacitor-secure-storage";
import { BASE, resolveApiUrl } from "@/api/client";
import { putToUploadUrl } from "@/api/media";
import { devicesService } from "@/services/devices";
import type { UUID } from "@/types";

// Native-only BLE relay for the XGSail E1 hardware device — implements
// docs/device-protocol.md §8 plus the E1-specific extensions documented in
// xgsail-e1's docs/ble-config.md (device_config, status, and control's
// calibrate/calibrate-reset/start-rec/stop-rec commands). No-op on web, same
// convention as nativeAuth.ts/nativeRecording.ts: Web Bluetooth isn't
// available on iOS Safari at all and is unreliable elsewhere, so BLE for
// XGSail E1 is a native-app-only feature by design (AddDeviceDialog hides/
// disables the card outside the native app rather than offering a shakier
// web fallback).
//
// GATT service/characteristic UUIDs — freshly generated (v4, random), not
// borrowed from a known public service like Nordic UART, so scanning for
// SERVICE_UUID can't false-positive-match an unrelated nearby BLE device
// that happens to implement that service. These are the values firmware
// must use (see docs/device-protocol.md §8.2 and xgsail-e1's
// docs/ble-config.md) — share this file or those docs with whoever
// implements the E1's BLE stack; nothing here depends on the specific
// values beyond app and firmware agreeing on them.
const SERVICE_UUID = "24e6db2c-3c8a-4b5b-ba5a-23bc4c818046";
const CHAR_IDENTITY = "985a1aae-858e-4727-9d5c-c8670bd6bd06";
const CHAR_PROVISIONING = "db2c2e63-9e13-4fa9-867c-0b579ce2ae57";
const CHAR_SESSION_MANIFEST = "ed9efdc8-70d4-4ce5-a0a3-9fa6d88b9b9e";
const CHAR_SESSION_DATA = "728d2815-0409-49ce-ad73-ecca6fc6d981";
const CHAR_CONTROL = "ec88dd3e-2562-420c-aebe-30a4ae40bdf9";
const CHAR_DEVICE_CONFIG = "042dfd7c-88f4-4ae8-af9a-eb1d7be7a3c6";
const CHAR_STATUS = "bfef7865-f3f7-486c-93fe-bbae78cfdc43";

const isNative = () => Capacitor.isNativePlatform();

// --- Stored device_api_key (per XGSail device, not a single global token —
// a user/boat/club can have several XGSail E1s claimed at once) -----------

function keyStorageKey(xgsailDeviceId: UUID): string {
  return `xgsail_device_key:${xgsailDeviceId}`;
}

export async function getStoredDeviceKey(xgsailDeviceId: UUID): Promise<string | null> {
  if (!isNative()) return null;
  try {
    return (await SecureStorage.getItem(keyStorageKey(xgsailDeviceId))) as string | null;
  } catch {
    // Corrupt/inaccessible keystore entry — same "treat as absent" handling
    // nativeAuth.ts uses for the refresh token.
    return null;
  }
}

async function storeDeviceKey(xgsailDeviceId: UUID, key: string): Promise<void> {
  await SecureStorage.setItem(keyStorageKey(xgsailDeviceId), key);
}

// --- Connection helper -------------------------------------------------

/** Connects, runs `fn`, always disconnects — the shared shape every BLE
 * operation in this file needs (claim, upload relay, config read/write,
 * status poll, commands). Centralized so connect/disconnect bookkeeping
 * doesn't get duplicated (and drift) across each operation. */
async function withConnection<T>(bleId: string, fn: () => Promise<T>): Promise<T> {
  await BleClient.initialize();
  await BleClient.connect(bleId);
  try {
    return await fn();
  } finally {
    await BleClient.disconnect(bleId).catch(() => {});
  }
}

// --- Scanning --------------------------------------------------------------

export interface ScannedDevice {
  bleId: string; // transient BLE connection id (BleClient.connect target)
  name: string | null;
}

/** Scans for nearby XGSail E1 devices for `timeoutMs` (default 8s) and
 * resolves with whatever was found by then. The claim dialog needs "what's
 * here" once to populate a picker, not a live-updating feed, so results are
 * collected into one list rather than streamed back through a callback. */
export async function scanForDevices(timeoutMs = 8000): Promise<ScannedDevice[]> {
  if (!isNative()) return [];
  await BleClient.initialize();
  const found = new Map<string, ScannedDevice>();
  await BleClient.requestLEScan({ services: [SERVICE_UUID] }, (result) => {
    found.set(result.device.deviceId, {
      bleId: result.device.deviceId,
      name: result.device.name ?? result.localName ?? null,
    });
  });
  await new Promise((resolve) => setTimeout(resolve, timeoutMs));
  await BleClient.stopLEScan();
  return [...found.values()];
}

interface IdentityPayload {
  external_id: string;
  firmware_version?: string;
}

async function readIdentity(bleId: string): Promise<IdentityPayload> {
  const raw = await BleClient.read(bleId, SERVICE_UUID, CHAR_IDENTITY);
  return JSON.parse(dataViewToText(raw)) as IdentityPayload;
}

// --- Resolving a claimed XGSail device to its live BLE peripheral -----------

// external_id -> bleId, populated by findByExternalId. There's no other way
// to map a claimed XGSail Device back to a nearby peripheral: every E1
// advertises under the same name ("SailFrames-E1"), so the only
// disambiguator is external_id read off `identity` after connecting — this
// cache just avoids re-scanning+re-connecting-to-everything on every poll.
const externalIdToBleId = new Map<string, string>();

/** Scans for `timeoutMs`, connecting to each candidate in turn until one's
 * `identity.external_id` matches, or none do. Cached by external_id; a
 * failed connect to the cached bleId (device moved out of range, rebooted
 * with a new OS-level connection id) evicts the cache entry so the next
 * call re-scans instead of retrying a dead id forever. */
export async function findByExternalId(
  externalId: string,
  timeoutMs = 8000,
): Promise<ScannedDevice | null> {
  if (!isNative()) return null;
  const cached = externalIdToBleId.get(externalId);
  if (cached) {
    try {
      const identity = await withConnection(cached, () => readIdentity(cached));
      if (identity.external_id === externalId) return { bleId: cached, name: null };
    } catch {
      // fall through to a fresh scan
    }
    externalIdToBleId.delete(externalId);
  }

  const candidates = await scanForDevices(timeoutMs);
  for (const candidate of candidates) {
    try {
      const identity = await withConnection(candidate.bleId, () => readIdentity(candidate.bleId));
      if (identity.external_id === externalId) {
        externalIdToBleId.set(externalId, candidate.bleId);
        return candidate;
      }
    } catch {
      // unreachable/errored candidate — try the next one
    }
  }
  return null;
}

/** Opens a connection the caller manages the lifetime of directly (unlike
 * withConnection's one-shot pattern) — for a panel that polls `status`/
 * `device_config` repeatedly while mounted instead of reconnecting per
 * call. Caller must call `disconnect()` on unmount. */
export async function connect(bleId: string): Promise<void> {
  await BleClient.initialize();
  await BleClient.connect(bleId);
}

export async function disconnect(bleId: string): Promise<void> {
  await BleClient.disconnect(bleId).catch(() => {});
}

// --- Claim over BLE (§8.3) --------------------------------------------------

/** Claims a device over BLE instead of typing the claim code onto it by
 * hand: connects, reads `external_id`, relays the (unauthenticated,
 * code-is-the-credential) claim/confirm call, writes the resulting key back
 * onto the device, and stores it locally — this phone becomes the natural
 * first upload relay for the device, since it already holds the key. */
export async function claimDevice(
  scanned: ScannedDevice,
  claimCode: string,
): Promise<{ deviceId: UUID; externalId: string }> {
  if (!isNative()) throw new Error("Not available on web");
  return withConnection(scanned.bleId, async () => {
    const identity = await readIdentity(scanned.bleId);
    const { device_id, device_api_key } = await devicesService.confirmClaim({
      external_id: identity.external_id,
      claim_code: claimCode,
    });
    await BleClient.write(
      scanned.bleId,
      SERVICE_UUID,
      CHAR_PROVISIONING,
      textToDataView(JSON.stringify({ device_api_key })),
    );
    await storeDeviceKey(device_id, device_api_key);
    return { deviceId: device_id, externalId: identity.external_id };
  });
}

// --- Upload relay (§8.4) ----------------------------------------------------

interface ManifestEntry {
  session_id: string; // the device-local SD path of the pending file — also
  // the source of the real filename (see uploadSessions below); NOT an
  // XGSail session id.
  byte_size: number;
  started_at: string;
  ended_at: string | null;
  // E1 extension (xgsail-e1's ble_relay.cpp/docs/ble-config.md): the
  // boat/activity the operator picked at recording start over `start-rec`,
  // if any. Absent = device/session-uploads defaults apply, same as a
  // direct-WiFi upload with no override.
  boat_id?: string;
  activity_id?: string;
}

/** The real basename the E1 would send if it uploaded this file itself over
 * WiFi (upload.cpp sends `filename` as the file's own SD basename, e.g.
 * `E1_20260723_1405_nav.csv`) — the manifest's `session_id` is that file's
 * full SD path. Using anything else here (a fixed "data.csv") makes the
 * backend's process_upload worker unable to tell nav/imu/wind/pressure CSVs
 * apart (it keys sensor type off the filename suffix) and, since every file
 * in one session shares `sequence_number=0` by default, collapses them onto
 * the same storage key — silently dropping every file but the last one
 * written. */
function basenameOf(sdPath: string): string {
  return sdPath.slice(sdPath.lastIndexOf("/") + 1);
}

async function writeControl(bleId: string, cmd: string, extra?: Record<string, unknown>): Promise<void> {
  await BleClient.write(
    bleId,
    SERVICE_UUID,
    CHAR_CONTROL,
    textToDataView(JSON.stringify({ cmd, ...extra })),
  );
}

// A dropped/stalled BLE link during a transfer must not hang the relay
// forever — the caller's retry (next uploadSessions() call, since the
// device hasn't received ack-uploaded and so hasn't freed its buffer) is the
// real recovery path, this timeout just bounds a single attempt.
const SESSION_TRANSFER_TIMEOUT_MS = 120_000;

/** Reassembles one session's bytes from `session_data` notifications, each
 * framed as a 4-byte big-endian sequence index + chunk payload (§8.2's wire
 * format). Resolves once it has received exactly `byteSize` bytes total —
 * the manifest-declared size is the completion signal, no separate
 * end-of-stream marker is needed. */
async function receiveSessionBytes(bleId: string, byteSize: number): Promise<Uint8Array<ArrayBuffer>> {
  const chunks = new Map<number, Uint8Array>();
  let received = 0;
  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(
      () => reject(new Error("Session transfer timed out")),
      SESSION_TRANSFER_TIMEOUT_MS,
    );
    BleClient.startNotifications(bleId, SERVICE_UUID, CHAR_SESSION_DATA, (value) => {
      if (value.byteLength < 4) return; // malformed frame — drop it, wait for a good one
      const index = value.getUint32(0, false);
      if (!chunks.has(index)) {
        chunks.set(index, new Uint8Array(value.buffer, value.byteOffset + 4, value.byteLength - 4));
        received += value.byteLength - 4;
      }
      if (received >= byteSize) {
        clearTimeout(timeout);
        resolve();
      }
    }).catch(reject);
  });
  await BleClient.stopNotifications(bleId, SERVICE_UUID, CHAR_SESSION_DATA).catch(() => {});

  // Explicitly a fresh (non-shared) ArrayBuffer, satisfying Blob's BlobPart
  // type below — the source chunks are views into DataView.buffer, which TS
  // widens to ArrayBufferLike (it could theoretically be a SharedArrayBuffer),
  // but this allocation is unambiguously a plain ArrayBuffer.
  const out: Uint8Array<ArrayBuffer> = new Uint8Array(received);
  let offset = 0;
  for (const [, chunk] of [...chunks.entries()].sort(([a], [b]) => a - b)) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
}

/** Calls a `DeviceKey`-authenticated endpoint (docs/device-protocol.md §3) —
 * deliberately NOT `api/client.ts`'s `api.*` helpers: those always send the
 * signed-in *user's* bearer token and CSRF header, which is the wrong
 * principal here (the app is relaying calls as the *device*, exactly as
 * `backend/routers/device_api.py` expects — no cookies, no CSRF, just the
 * device key). Mirrors the backend's own separation between user routers
 * and the device-facing router. */
async function deviceApiFetch<T>(
  deviceKey: string,
  path: string,
  method: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      Authorization: `DeviceKey ${deviceKey}`,
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`Device API ${method} ${path} failed (${res.status})`);
  if (res.status === 204) return null as T;
  return (await res.json()) as T;
}

export interface UploadRelayResult {
  sessionId: string;
  uploaded: boolean;
  error?: string;
}

/** Relays every session the device has buffered but couldn't upload itself
 * (no WiFi at the time) through this phone's own connection. Safe to call
 * repeatedly, including after a dropped connection: `session-uploads` (§4.1)
 * is idempotent on `(session, device, sequence_number)`, so re-opening the
 * same session's upload on retry returns the same `session_upload_id` with
 * a fresh URL instead of duplicating it — the device only frees its local
 * buffer once it receives `ack-uploaded`, so an interrupted relay is simply
 * retried the next time this runs, nothing is lost or duplicated. */
export async function uploadSessions(
  scanned: ScannedDevice,
  xgsailDeviceId: UUID,
): Promise<UploadRelayResult[]> {
  if (!isNative()) return [];
  const key = await getStoredDeviceKey(xgsailDeviceId);
  if (!key) throw new Error("No stored key for this device — claim it again");

  return withConnection(scanned.bleId, async () => {
    const results: UploadRelayResult[] = [];
    const manifestRaw = await BleClient.read(scanned.bleId, SERVICE_UUID, CHAR_SESSION_MANIFEST);
    const manifest = JSON.parse(dataViewToText(manifestRaw)) as ManifestEntry[];

    for (const entry of manifest) {
      try {
        await writeControl(scanned.bleId, "start-transfer", { session_id: entry.session_id });
        const bytes = await receiveSessionBytes(scanned.bleId, entry.byte_size);

        // filename is the file's real SD basename (nav/imu/wind/pres suffix
        // intact) — see basenameOf()'s doc for why a fixed name breaks
        // sensor-type detection and collides multiple files onto one key.
        // boat_id/activity_id, when the operator chose them at recording
        // start, must be forwarded here too so a BLE-relayed upload behaves
        // like a direct-WiFi one (upload.cpp forwards the same fields).
        const upload = await deviceApiFetch<{ session_upload_id: UUID; upload_url: string }>(
          key,
          "/devices/me/session-uploads",
          "POST",
          {
            started_at: entry.started_at,
            ended_at: entry.ended_at,
            filename: basenameOf(entry.session_id),
            ...(entry.boat_id ? { boat_id: entry.boat_id } : {}),
            ...(entry.activity_id ? { activity_id: entry.activity_id } : {}),
          },
        );

        await putToUploadUrl(resolveApiUrl(upload.upload_url), new Blob([bytes]));
        await deviceApiFetch(key, `/devices/me/session-uploads/${upload.session_upload_id}`, "PATCH", {
          is_final: true,
        });
        await writeControl(scanned.bleId, "ack-uploaded", { session_id: entry.session_id });
        results.push({ sessionId: entry.session_id, uploaded: true });
      } catch (err) {
        results.push({
          sessionId: entry.session_id,
          uploaded: false,
          error: err instanceof Error ? err.message : String(err),
        });
      }
    }
    return results;
  });
}

// --- device_config (xgsail-e1's docs/ble-config.md) -------------------------

export interface E1WifiNetwork {
  ssid: string;
  pass: string; // always "" on read (write-only) — see ble-config.md
}

export interface E1Config {
  boat_id: string; // mesh-identity/log-filename label — NOT the XGSail boat
  unit_role: "racing_boat" | "rc_signal" | "rc_pin" | "mark" | "committee_chase" | "spare";
  api_base_url: string;
  wind_mac: string;
  wind_offset: number;
  // stop_speed_knots/start_delay_sec/stop_delay_sec are round-tripped by the
  // firmware for older cards' config.txt compatibility but unused by it
  // (xgsail-e1's docs/ble-config.md) — deliberately not modeled here.
  start_speed_knots: number;
  rtk_enabled: boolean;
  auto_cleanup_uploads: boolean;
  wifi: E1WifiNetwork[];
}

export type E1ConfigPatch = Partial<Omit<E1Config, "wifi">> & { wifi?: E1WifiNetwork[] };

export async function readConfig(bleId: string): Promise<E1Config> {
  const raw = await BleClient.read(bleId, SERVICE_UUID, CHAR_DEVICE_CONFIG);
  return JSON.parse(dataViewToText(raw)) as E1Config;
}

export type ConfigWriteErrorReason = "pairing_window_closed" | "bad_json" | "sd_busy";

export class ConfigWriteError extends Error {
  constructor(public reason: ConfigWriteErrorReason) {
    super(`device_config write failed: ${reason}`);
  }
}

/** Writes a partial config update and awaits the device's notified result.
 * A write outside the pairing window (no recent long-press, no existing
 * bond) is rejected with `pairing_window_closed` — the caller is
 * responsible for telling the user to long-press the physical button
 * first (xgsail-e1's docs/ble-config.md: no in-band way to open it). */
export async function writeConfig(bleId: string, patch: E1ConfigPatch): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    BleClient.startNotifications(bleId, SERVICE_UUID, CHAR_DEVICE_CONFIG, (value) => {
      const status = JSON.parse(dataViewToText(value)) as { status: "ok" | "error"; reason?: ConfigWriteErrorReason };
      void BleClient.stopNotifications(bleId, SERVICE_UUID, CHAR_DEVICE_CONFIG).catch(() => {});
      if (status.status === "ok") resolve();
      else reject(new ConfigWriteError(status.reason ?? "bad_json"));
    })
      .then(() =>
        BleClient.write(bleId, SERVICE_UUID, CHAR_DEVICE_CONFIG, textToDataView(JSON.stringify(patch))),
      )
      .catch(reject);
  });
}

// --- status (xgsail-e1's docs/ble-config.md) --------------------------------

export interface E1Status {
  claimed: boolean;
  firmware_version: string;
  uptime_s: number;
  heap_free: number;
  battery: { pct: number; v: number; critical: boolean };
  sd_ok: boolean;
  wifi: { connected: boolean; ssid?: string; ip?: string };
  sensors: { imu: boolean; pressure: boolean; wind: boolean };
  gps: {
    fix: boolean;
    satellites: number;
    hdop: number;
    lat: number;
    lon: number;
    speed_kts: number;
    course: number;
  };
  wind: { connected: boolean; speed_kts?: number; angle_deg?: number; battery?: number };
  // elapsed_s is only present while logging is true (xgsail-e1's docs/ble-config.md).
  recording: { logging: boolean; session_count: number; pending_uploads: number; elapsed_s?: number };
}

export async function readStatus(bleId: string): Promise<E1Status> {
  const raw = await BleClient.read(bleId, SERVICE_UUID, CHAR_STATUS);
  return JSON.parse(dataViewToText(raw)) as E1Status;
}

// --- control commands: calibrate / start-rec / stop-rec ---------------------

export interface CalibrateResult {
  status: "ok" | "error";
  heel_offset?: number;
  pitch_offset?: number;
  reason?: "no_imu" | "sd_busy";
}

export interface RecCommandResult {
  ok: boolean;
  logging: boolean;
}

/** Sends a `control` command and awaits its notified reply, matched by
 * `cmd` (control is used for several concurrent purposes — start-transfer/
 * ack-uploaded during a relay, calibrate/rec commands here — so replies are
 * correlated by the `cmd` field, not by connection state). */
async function sendControlCommand<T>(bleId: string, cmd: string, extra?: Record<string, unknown>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`No response to '${cmd}'`)), 10_000);
    BleClient.startNotifications(bleId, SERVICE_UUID, CHAR_CONTROL, (value) => {
      const payload = JSON.parse(dataViewToText(value)) as { cmd?: string } & Record<string, unknown>;
      if (payload.cmd !== cmd) return;
      clearTimeout(timeout);
      void BleClient.stopNotifications(bleId, SERVICE_UUID, CHAR_CONTROL).catch(() => {});
      resolve(payload as T);
    })
      .then(() => writeControl(bleId, cmd, extra))
      .catch((err) => {
        clearTimeout(timeout);
        reject(err);
      });
  });
}

/** Zeroes heel/pitch at the boat's current attitude — only meaningful with
 * the boat sitting level; the caller is responsible for telling the user
 * that first. */
export function calibrate(bleId: string): Promise<CalibrateResult> {
  return sendControlCommand<CalibrateResult>(bleId, "calibrate");
}

/** Resets heel/pitch calibration offsets back to zero. */
export function calibrateReset(bleId: string): Promise<CalibrateResult> {
  return sendControlCommand<CalibrateResult>(bleId, "calibrate-reset");
}

/** Starts a recording on the device, same entry point as the physical
 * button's short press. `boatId`/`activityId` are both optional and
 * independent of each other (xgsail-e1's docs/ble-config.md): omitting both
 * files the session under the device's own boat and a fresh solo activity,
 * same as today's default. */
export function startRec(
  bleId: string,
  opts?: { boatId?: UUID; activityId?: UUID },
): Promise<RecCommandResult> {
  return sendControlCommand<RecCommandResult>(bleId, "start-rec", {
    ...(opts?.boatId ? { boat_id: opts.boatId } : {}),
    ...(opts?.activityId ? { activity_id: opts.activityId } : {}),
  });
}

export function stopRec(bleId: string): Promise<RecCommandResult> {
  return sendControlCommand<RecCommandResult>(bleId, "stop-rec");
}
