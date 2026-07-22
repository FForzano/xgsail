import { Capacitor } from "@capacitor/core";
import { BleClient, dataViewToText, textToDataView } from "@capacitor-community/bluetooth-le";
import { SecureStorage } from "@aparajita/capacitor-secure-storage";
import { BASE, resolveApiUrl } from "@/api/client";
import { putToUploadUrl } from "@/api/media";
import { devicesService } from "@/services/devices";
import type { UUID } from "@/types";

// Native-only BLE relay for the XGSail E1 hardware device — implements
// docs/device-protocol.md §8. No-op on web, same convention as
// nativeAuth.ts/nativeRecording.ts: Web Bluetooth isn't available on iOS
// Safari at all and is unreliable elsewhere, so BLE claim/upload for
// XGSail E1 is a native-app-only feature by design (AddDeviceDialog hides/
// disables the card outside the native app rather than offering a shakier
// web fallback).
//
// Two operations, both documented in the protocol doc:
// - claimDevice()   — §8.3: relays the claim/confirm call and writes the
//   resulting device_api_key onto the device over BLE.
// - uploadSessions() — §8.4: relays buffered sessions the device couldn't
//   upload itself (no WiFi at the time) through the phone's own connection.
//
// GATT service/characteristic UUIDs — freshly generated (v4, random), not
// borrowed from a known public service like Nordic UART, so scanning for
// SERVICE_UUID can't false-positive-match an unrelated nearby BLE device
// that happens to implement that service. These are the values firmware
// must use (see docs/device-protocol.md §8.2) — share this file or the doc
// with whoever implements the E1's BLE stack; nothing here depends on the
// specific values beyond app and firmware agreeing on them.
const SERVICE_UUID = "24e6db2c-3c8a-4b5b-ba5a-23bc4c818046";
const CHAR_IDENTITY = "985a1aae-858e-4727-9d5c-c8670bd6bd06";
const CHAR_PROVISIONING = "db2c2e63-9e13-4fa9-867c-0b579ce2ae57";
const CHAR_SESSION_MANIFEST = "ed9efdc8-70d4-4ce5-a0a3-9fa6d88b9b9e";
const CHAR_SESSION_DATA = "728d2815-0409-49ce-ad73-ecca6fc6d981";
const CHAR_CONTROL = "ec88dd3e-2562-420c-aebe-30a4ae40bdf9";

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
  await BleClient.initialize();
  await BleClient.connect(scanned.bleId);
  try {
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
  } finally {
    await BleClient.disconnect(scanned.bleId).catch(() => {});
  }
}

// --- Upload relay (§8.4) ----------------------------------------------------

interface ManifestEntry {
  session_id: string;
  byte_size: number;
  started_at: string;
  ended_at: string | null;
}

async function writeControl(bleId: string, cmd: string, sessionId: string): Promise<void> {
  await BleClient.write(
    bleId,
    SERVICE_UUID,
    CHAR_CONTROL,
    textToDataView(JSON.stringify({ cmd, session_id: sessionId })),
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

  await BleClient.initialize();
  await BleClient.connect(scanned.bleId);
  const results: UploadRelayResult[] = [];
  try {
    const manifestRaw = await BleClient.read(scanned.bleId, SERVICE_UUID, CHAR_SESSION_MANIFEST);
    const manifest = JSON.parse(dataViewToText(manifestRaw)) as ManifestEntry[];

    for (const entry of manifest) {
      try {
        await writeControl(scanned.bleId, "start-transfer", entry.session_id);
        const bytes = await receiveSessionBytes(scanned.bleId, entry.byte_size);

        // boat_id omitted: XGSail E1 is a "boat_tracker"-category device
        // type, so the backend defaults it to the device's own owner_boat_id
        // (backend/routers/device_api.py) — same as a direct-WiFi upload.
        const upload = await deviceApiFetch<{ session_upload_id: UUID; upload_url: string }>(
          key,
          "/devices/me/session-uploads",
          "POST",
          { started_at: entry.started_at, ended_at: entry.ended_at, filename: "data.csv" },
        );

        await putToUploadUrl(resolveApiUrl(upload.upload_url), new Blob([bytes]));
        await deviceApiFetch(key, `/devices/me/session-uploads/${upload.session_upload_id}`, "PATCH", {
          is_final: true,
        });
        await writeControl(scanned.bleId, "ack-uploaded", entry.session_id);
        results.push({ sessionId: entry.session_id, uploaded: true });
      } catch (err) {
        results.push({
          sessionId: entry.session_id,
          uploaded: false,
          error: err instanceof Error ? err.message : String(err),
        });
      }
    }
  } finally {
    await BleClient.disconnect(scanned.bleId).catch(() => {});
  }
  return results;
}
