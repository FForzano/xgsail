import { Capacitor } from "@capacitor/core";
import { Directory, Filesystem } from "@capacitor/filesystem";
import { SecureStorage } from "@aparajita/capacitor-secure-storage";
import * as e1 from "@xgsail-e1/capacitor";
import { devicesService, XGSAIL_WATCH_PARSER_KEY } from "@/services/devices";
import { relayBundle } from "@/services/deviceUpload";
import type { BundleFile } from "@/services/deviceUpload";
import { WatchBridge } from "@/plugins/watchBridge";
import type { WatchSessionReceivedEvent } from "@/plugins/watchBridge";
import type { UUID } from "@/types";

// Native-only (iOS) glue for the Apple Watch companion. The watch records a
// session standalone, then transfers the finished CSV bundle to the phone over
// WatchConnectivity; the native WatchBridge plugin stores the files and fires
// `watchSessionReceived`. This module relays that bundle to the backend via
// the device protocol (docs/device-protocol.md §9), authenticating as the
// wearable device whose key the phone holds. No-ops on web, same convention as
// nativeRecording.ts / nativeAuth.ts; dynamically imported so it never lands
// in the web bundle.

// The watch's device_api_key lives in the same Keychain namespace the E1 uses
// (keyed by XGSail device id — the watch's id differs, so no collision).
const keyStore = e1.secureStorageKeyStore("xgsail_device_key");

// Non-secret watch identity, persisted so the phone can keep relaying after a
// restart. The api key itself is the secret and stays in `keyStore` above.
const WATCH_DEVICE_ID_KEY = "xgsail_watch_device_id";
const WATCH_EXTERNAL_ID_KEY = "xgsail_watch_external_id";

/** True on iOS with a paired, app-installed watch — recording/claiming is only
 * offered then. */
export async function isSupported(): Promise<boolean> {
  if (Capacitor.getPlatform() !== "ios") return false;
  try {
    return (await WatchBridge.isSupported()).supported;
  } catch {
    return false;
  }
}

/** The claimed watch's XGSail device id, or null if this phone hasn't claimed
 * one (or it was revoked). */
export async function getClaimedDeviceId(): Promise<UUID | null> {
  if (!Capacitor.isNativePlatform()) return null;
  try {
    const id = (await SecureStorage.getItem(WATCH_DEVICE_ID_KEY)) as string | null;
    if (!id) return null;
    // Confirm the phone still holds the device key (rotated/revoked ⇒ gone).
    return (await keyStore.load(id)) ? (id as UUID) : null;
  } catch {
    return null;
  }
}

async function getOrCreateExternalId(): Promise<string> {
  const existing = (await SecureStorage.getItem(WATCH_EXTERNAL_ID_KEY)) as string | null;
  if (existing) return existing;
  // Stable per install: the physical watch has no server-usable serial we can
  // read, so the phone mints one and persists it as the device's external_id.
  const generated = `applewatch-${crypto.randomUUID()}`;
  await SecureStorage.setItem(WATCH_EXTERNAL_ID_KEY, generated);
  return generated;
}

/** Claim this user's Apple Watch as a personal `wearable` device. The phone is
 * a pure relay (docs/device-protocol.md §8.3): it creates the claim, redeems
 * it itself, and stores the returned device key — the watch never needs it.
 * Returns the XGSail device id. */
export async function claimWatch(userId: UUID, nickname?: string): Promise<UUID> {
  if (!(await isSupported())) {
    throw new Error("No paired Apple Watch with the XGSail app found");
  }
  const types = await devicesService.listTypes();
  const watchType = types.find((dt) => dt.parser_key === XGSAIL_WATCH_PARSER_KEY);
  if (!watchType) throw new Error("Apple Watch device type not found on the server");

  const ticket = await devicesService.createClaim({
    device_type_id: watchType.id,
    owner_user_id: userId,
    nickname,
  });
  const externalId = await getOrCreateExternalId();
  const confirmed = await devicesService.confirmClaim({
    external_id: externalId,
    claim_code: ticket.claim_code,
  });
  await keyStore.save(confirmed.device_id, confirmed.device_api_key);
  await SecureStorage.setItem(WATCH_DEVICE_ID_KEY, confirmed.device_id);
  return confirmed.device_id as UUID;
}

/** Forget the local claim (after the user revokes the device server-side). */
export async function forgetWatch(): Promise<void> {
  const id = (await SecureStorage.getItem(WATCH_DEVICE_ID_KEY)) as string | null;
  if (id) {
    try {
      await keyStore.save(id, "");
    } catch {
      // best effort
    }
  }
  await SecureStorage.removeItem(WATCH_DEVICE_ID_KEY);
  await SecureStorage.removeItem(WATCH_EXTERNAL_ID_KEY);
}

/** Push boat + recording mode to the watch so its readouts and the upload
 * subject are set before the operator starts recording. */
export async function sendContext(opts: {
  boatId?: UUID | null;
  mode?: "boat" | "personal";
}): Promise<void> {
  const deviceClaimed = (await getClaimedDeviceId()) !== null;
  await WatchBridge.sendContext({ boatId: opts.boatId ?? null, mode: opts.mode, deviceClaimed });
}

// Filename suffix → which subject the file belongs to. GPS is the boat track
// (or personal, per mode); the physiological files are always the wearer's.
const GPS_SUFFIX = "_nav.csv";
const PHYSIO_SUFFIXES = ["_hr.csv", "_energy.csv", "_hrv.csv", "_resp.csv"];

async function readBundleFile(dir: string, name: string): Promise<BundleFile> {
  const { data } = await Filesystem.readFile({
    path: `${dir}/${name}`,
    directory: Directory.Data,
  });
  // Filesystem returns base64 for binary reads and a string on some platforms;
  // normalize to a Blob the same way nativeRecording.readRecordingGpx does.
  const blob =
    typeof data === "string"
      ? await (await fetch(`data:text/csv;base64,${data}`)).blob()
      : data;
  return { filename: name, blob };
}

/** Relay one received watch session to the backend: the GPS file as one
 * subject and the physiological files as the crew_member subject, both under
 * the same boat + start time so they merge into one session. `userId` is the
 * wearer (subject_user_id for the physiological streams). */
export async function relaySession(
  event: WatchSessionReceivedEvent,
  userId: UUID,
): Promise<void> {
  const deviceId = await getClaimedDeviceId();
  if (!deviceId) throw new Error("Apple Watch is not claimed on this phone");
  const deviceKey = await keyStore.load(deviceId);
  if (!deviceKey) throw new Error("No device key stored for the watch");
  if (!event.boatId) throw new Error("Watch session has no boat selected");

  const gpsFiles = event.files.filter((f) => f.includes(GPS_SUFFIX));
  const physioFiles = event.files.filter((f) => PHYSIO_SUFFIXES.some((s) => f.includes(s)));

  // seq 0 — GPS. subject_type=boat unless the operator chose personal-only.
  if (gpsFiles.length > 0) {
    const files = await Promise.all(gpsFiles.map((n) => readBundleFile(event.dir, n)));
    await relayBundle({
      deviceKey,
      boatId: event.boatId as UUID,
      startedAt: event.startedAt,
      endedAt: event.endedAt,
      sequenceNumber: 0,
      subjectType: event.mode === "personal" ? "crew_member" : "boat",
      subjectUserId: event.mode === "personal" ? userId : null,
      files,
    });
  }

  // seq 1 — physiological streams, always the wearer's own (crew_member).
  if (physioFiles.length > 0) {
    const files = await Promise.all(physioFiles.map((n) => readBundleFile(event.dir, n)));
    await relayBundle({
      deviceKey,
      boatId: event.boatId as UUID,
      startedAt: event.startedAt,
      endedAt: event.endedAt,
      sequenceNumber: 1,
      subjectType: "crew_member",
      subjectUserId: userId,
      files,
    });
  }

  // Uploaded — let the plugin drop the local files (and ack the watch, which
  // frees the watch's own buffer). Only reached on success, so nothing is
  // deleted until it's safely on the backend.
  await WatchBridge.ackSession({ sessionId: event.sessionId });
}

// Single relay pass in flight at a time — the live event and the
// launch/foreground retries all funnel through relayPending, and a call made
// while one is running is a no-op (the next trigger picks up anything missed).
let relaying = false;

/** Relay every session the phone still holds (received but not yet uploaded).
 * Durable + idempotent: sessions persist across relaunches (plugin
 * manifest.json) and are deleted only after a successful upload, so an upload
 * that failed while offline is simply retried on the next call — nothing
 * accumulates and nothing is lost. Safe to call repeatedly/concurrently. */
export async function relayPending(
  userId: UUID,
  onResult?: (event: WatchSessionReceivedEvent, error: Error | null) => void,
): Promise<void> {
  if (!Capacitor.isNativePlatform() || relaying) return;
  relaying = true;
  try {
    const { sessions } = await WatchBridge.listPendingSessions();
    for (const event of sessions) {
      try {
        await relaySession(event, userId);
        onResult?.(event, null);
      } catch (e) {
        // Keep the files for the next retry; report but don't abort the batch.
        onResult?.(event, e instanceof Error ? e : new Error(String(e)));
      }
    }
  } finally {
    relaying = false;
  }
}

/** Subscribe to watch sessions arriving from the paired watch; each arrival
 * triggers a `relayPending` pass (which also sweeps up anything left from a
 * previous offline attempt). Returns an unsubscribe function. `userId` is the
 * current signed-in user. */
export async function subscribe(
  userId: UUID,
  onResult: (event: WatchSessionReceivedEvent, error: Error | null) => void,
): Promise<() => void> {
  if (!Capacitor.isNativePlatform()) return () => {};
  const handle = await WatchBridge.addListener("watchSessionReceived", () => {
    void relayPending(userId, onResult);
  });
  return () => {
    void handle.remove();
  };
}
