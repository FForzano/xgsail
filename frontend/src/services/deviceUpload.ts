import { BASE } from "@/api/client";
import { putToUploadUrl } from "@/api/media";
import type { UUID } from "@/types";

// Device-protocol upload relay (docs/device-protocol.md §4): open a
// session-upload → PUT the raw bytes to the presigned URL → PATCH it final.
//
// These calls authenticate as the *device* (`Authorization: DeviceKey <key>`),
// never as the logged-in user — so they deliberately bypass the `api` client
// (which injects the user Bearer token + refresh logic) and talk to the
// backend directly with `credentials: "omit"`, exactly like
// `@xgsail-e1/capacitor`'s `httpBackend`. We don't reuse that package's
// `uploadSession` here because it only covers the E1's shape — one file,
// `subject_type=boat`, `sequence_number=0`, `is_final=true` — whereas a
// wearable relays a *multi-file, multi-subject, sequenced* bundle (the watch's
// GPS as one subject and its physiological streams as another). This helper is
// the shared home for that fuller relay; the watch relay in `nativeWatch.ts`
// is its only caller today.

export interface OpenUploadParams {
  boatId: UUID;
  /** ISO 8601 with offset. Same boat + started_at across uploads makes the
   * backend's find_or_create_session merge them into one session. */
  startedAt: string;
  endedAt?: string | null;
  activityId?: UUID | null;
  /** 0 = first/only bundle; a second bundle in the same session (e.g. a
   * different subject from the same device) uses 1, and so on. */
  sequenceNumber?: number;
  isFinal?: boolean;
  subjectType?: "boat" | "crew_member";
  /** Required by the backend when subjectType is "crew_member". */
  subjectUserId?: UUID | null;
  /** Object basename for the file being PUT — the worker keys sensor type off
   * this, so every file in a bundle needs its real distinct name. */
  filename: string;
}

export interface OpenUploadResult {
  session_upload_id: UUID;
  session_id: UUID;
  activity_id: UUID | null;
  upload_url: string;
  upload_url_expires_at: string;
}

async function deviceApiFetch<T>(
  deviceKey: string,
  path: string,
  method: "POST" | "PATCH",
  body: unknown,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    // Device protocol is DeviceKey-authenticated, never cookie-based.
    credentials: "omit",
    headers: {
      "Content-Type": "application/json",
      Authorization: `DeviceKey ${deviceKey}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Device API ${method} ${path} failed (${res.status})${text ? `: ${text}` : ""}`);
  }
  return (await res.json()) as T;
}

/** Open (or re-open — idempotent on `(session, device, sequence_number)`) a
 * session-upload and get a fresh presigned URL for `params.filename`. */
export function openSessionUpload(
  deviceKey: string,
  params: OpenUploadParams,
): Promise<OpenUploadResult> {
  return deviceApiFetch<OpenUploadResult>(deviceKey, "/devices/me/session-uploads", "POST", {
    boat_id: params.boatId,
    started_at: params.startedAt,
    ended_at: params.endedAt ?? null,
    activity_id: params.activityId ?? null,
    sequence_number: params.sequenceNumber ?? 0,
    is_final: params.isFinal ?? true,
    subject_type: params.subjectType ?? "boat",
    subject_user_id: params.subjectUserId ?? null,
    filename: params.filename,
  });
}

export function patchSessionUpload(
  deviceKey: string,
  uploadId: UUID,
  body: { is_final?: boolean; status?: "failed" },
): Promise<unknown> {
  return deviceApiFetch(deviceKey, `/devices/me/session-uploads/${uploadId}`, "PATCH", body);
}

export interface BundleFile {
  filename: string;
  blob: Blob;
}

export interface RelayBundleParams {
  deviceKey: string;
  boatId: UUID;
  startedAt: string;
  endedAt?: string | null;
  activityId?: UUID | null;
  sequenceNumber: number;
  subjectType: "boat" | "crew_member";
  subjectUserId?: UUID | null;
  files: BundleFile[];
}

/** Relay one session-upload (one or more files sharing a `sequence_number`)
 * end-to-end: open per file (idempotent — every file returns the same
 * `session_upload_id` with its own fresh URL), PUT each, then PATCH the upload
 * final once. Returns the backend `session_id` the bundle landed in. */
export async function relayBundle(params: RelayBundleParams): Promise<UUID> {
  if (params.files.length === 0) throw new Error("relayBundle: no files");
  let uploadId: UUID | null = null;
  let sessionId: UUID | null = null;
  for (const file of params.files) {
    const opened = await openSessionUpload(params.deviceKey, {
      boatId: params.boatId,
      startedAt: params.startedAt,
      endedAt: params.endedAt,
      activityId: params.activityId,
      sequenceNumber: params.sequenceNumber,
      // Row is created on the first open; later files just fetch a URL. PATCH
      // below is what actually finalizes, so opening non-final is safe.
      isFinal: false,
      subjectType: params.subjectType,
      subjectUserId: params.subjectUserId,
      filename: file.filename,
    });
    uploadId = opened.session_upload_id;
    sessionId = opened.session_id;
    await putToUploadUrl(opened.upload_url, file.blob, "application/octet-stream");
  }
  await patchSessionUpload(params.deviceKey, uploadId!, { is_final: true });
  return sessionId!;
}
