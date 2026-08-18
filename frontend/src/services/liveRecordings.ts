import { api } from "@/api/client";
import type { LiveRecording, UUID } from "@/types";

export const liveRecordingKeys = {
  all: ["live-recordings"] as const,
};

/** Presence for in-progress recordings — "is anybody else aboard recording
 * this outing right now". Nothing here creates a session, and every call is
 * best-effort: a recording proceeds whether or not any of them succeed. */
export const liveRecordingsService = {
  list: () => api.get<LiveRecording[]>("/live-recordings"),

  /** Announce a recording, or keep an announced one alive — one call for
   * both, idempotent on `client_recording_id`, so the app can simply retry
   * whenever connectivity returns. */
  upsert: (body: { boat_id: UUID; activity_id?: UUID | null; client_recording_id: string }) =>
    api.put<LiveRecording>("/live-recordings", {
      boat_id: body.boat_id,
      activity_id: body.activity_id ?? null,
      client_recording_id: body.client_recording_id,
    }),

  end: (boatId: UUID) => api.del(`/live-recordings?boat_id=${boatId}`),
};
