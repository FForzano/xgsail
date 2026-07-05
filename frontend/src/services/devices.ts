import { api } from "@/api/client";
import type { ClaimTicket, Device, DeviceHealth, DeviceType, UUID } from "@/types";

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

  listTypes: () => api.get<DeviceType[]>("/device-types"),
  createType: (body: Partial<DeviceType>) => api.post<DeviceType>("/device-types", body),
  updateType: (id: UUID, body: Partial<DeviceType>) =>
    api.patch<DeviceType>(`/device-types/${id}`, body),
  removeType: (id: UUID) => api.del(`/device-types/${id}`),
};
