import { api } from "@/api/client";
import type { ClaimTicket, Device, DeviceHealth, DeviceType, UUID } from "@/types";

// The XGSail E1's device-type row is still seeded as "SailFrames E1" (see
// backend/auth/seed.py) — matching on `parser_key` rather than `name` keeps
// this working regardless of whether/when that display name gets renamed,
// and (unlike `category`, which "Generic GPX" also shares) it uniquely
// identifies the E1 hardware adapter.
export const XGSAIL_E1_PARSER_KEY = "sailframes_e1_csv";

// The Apple Watch companion's device-type row (backend/auth/seed.py). Like
// the E1, matched on parser_key rather than the display name.
export const XGSAIL_WATCH_PARSER_KEY = "xgsail_watch_csv";

/** Whether `device` is a claimed XGSail E1, given the full `DeviceType` list
 * (from `listTypes`) — the parser_key match is the only reliable
 * disambiguator, see the note on XGSAIL_E1_PARSER_KEY above. */
export function isE1Device(
  device: Pick<Device, "device_type_id" | "status"> | undefined,
  types: DeviceType[] | undefined,
): boolean {
  return (
    !!device &&
    device.status === "claimed" &&
    types?.find((dt) => dt.id === device.device_type_id)?.parser_key === XGSAIL_E1_PARSER_KEY
  );
}

export const deviceKeys = {
  all: ["devices"] as const,
  detail: (id: UUID) => ["devices", id] as const,
  health: (id: UUID) => ["devices", id, "health"] as const,
  types: ["device-types"] as const,
};

export const devicesService = {
  list: () => api.get<Device[]>("/devices"),
  get: (id: UUID) => api.get<Device>(`/devices/${id}`),
  update: (id: UUID, body: { nickname?: string }) => api.patch<Device>(`/devices/${id}`, body),
  revoke: (id: UUID) => api.del(`/devices/${id}`),
  health: (id: UUID) => api.get<DeviceHealth>(`/devices/${id}/health`),
  rotateKey: (id: UUID) =>
    api.post<{ device_id: UUID; device_api_key: string }>(`/devices/${id}/rotate-key`),

  /** Exactly one of owner_user_id / owner_boat_id / owner_club_id. */
  createClaim: (body: {
    device_type_id: UUID;
    nickname?: string;
    owner_user_id?: UUID;
    owner_boat_id?: UUID;
    owner_club_id?: UUID;
  }) => api.post<ClaimTicket>("/devices/claims", body),

  /** Redeems a claim code — normally called by the device itself
   * (docs/device-protocol.md §2 step 3); called from here only by the native
   * app's BLE relay (§8.3), which reads `external_id` off the device over
   * BLE and performs this call on its behalf. Unauthenticated on the
   * backend (the claim code is the credential), so this works even for a
   * signed-out relay call. */
  confirmClaim: (body: { external_id: string; claim_code: string }) =>
    api.post<{ device_id: UUID; device_api_key: string; issued_at: string }>(
      "/devices/claim/confirm",
      body,
    ),

  listTypes: () => api.get<DeviceType[]>("/device-types"),
  createType: (body: Partial<DeviceType>) => api.post<DeviceType>("/device-types", body),
  updateType: (id: UUID, body: Partial<DeviceType>) =>
    api.patch<DeviceType>(`/device-types/${id}`, body),
  removeType: (id: UUID) => api.del(`/device-types/${id}`),
};
