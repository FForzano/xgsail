import { useEffect, useRef } from "react";
import { Capacitor } from "@capacitor/core";
import * as nativeRecording from "@/services/nativeRecording";
import { liveRecordingsService } from "@/services/liveRecordings";
import type { RecordingMeta } from "@/services/nativeRecording";
import type { UUID } from "@/types";

// Against the backend's 20-minute staleness window (LIVE_STALE_AFTER), so
// three beats can go missing before the banner drops the recording.
const HEARTBEAT_MS = 5 * 60_000;

/** Tells the backend a recording is running, so the rest of the boat's crew
 * can see it and join the same outing.
 *
 * Lives here rather than in `services/nativeRecording.ts`, which is
 * deliberately free of API and auth imports — the recording lifecycle has to
 * keep working with no server at all, and coupling it to the API client would
 * end that. Nor in `RegistraPage`, which unmounts the moment the user goes to
 * the diary while the recording carries on. `AppShell` mounts it once, next to
 * the other headless background services.
 *
 * Every call is best-effort and swallowed: presence is a convenience, and a
 * failure here must never touch the recordings index or interrupt a
 * recording.
 *
 * The heartbeat rides two clocks. A plain interval covers the app in the
 * foreground; `nativeRecording`'s index notification — which fires on every
 * persisted fix, including while the app is backgrounded — covers the rest of
 * the outing, when a WebView's timers are suspended and a phone is in a
 * pocket. Both go through the same throttle, so the extra path costs nothing
 * when the interval is already keeping up.
 */
export function useLiveRecordingPresence(userId: UUID | undefined, enabled: boolean): void {
  const { recordings } = nativeRecording.useRecordings();
  const active = recordings.find(
    (r) => r.status === "recording" || r.status === "paused",
  );
  // An orphan of a dead app process has already been reconciled to
  // "interrupted" by the time this list is readable, so an entry that still
  // says "recording" really is one.
  const lastBeatAt = useRef(0);
  const announced = useRef<{ id: UUID; boatId: UUID } | null>(null);

  const on = enabled && Capacitor.isNativePlatform() && !!userId;

  useEffect(() => {
    if (!on || !active) return;

    const beat = (recording: RecordingMeta) => {
      lastBeatAt.current = Date.now();
      announced.current = { id: recording.id, boatId: recording.boatId };
      void liveRecordingsService
        .upsert({
          boat_id: recording.boatId,
          activity_id: recording.activityId,
          client_recording_id: recording.id,
        })
        .catch(() => {
          // Offline, or not a member of this boat. Either way the recording
          // carries on; the next beat retries, and the call is idempotent.
        });
    };

    beat(active);
    const id = window.setInterval(() => beat(active), HEARTBEAT_MS);
    return () => window.clearInterval(id);
    // boatId/activityId are in the deps because a heartbeat carries them:
    // reassigning the outing mid-recording has to reach the banner.
  }, [on, active?.id, active?.boatId, active?.activityId]);

  // The background path. `useRecordings` re-publishes on every persisted fix,
  // which is the one thing still running when the app is backgrounded.
  useEffect(() => {
    if (!on || !active) return;
    if (Date.now() - lastBeatAt.current < HEARTBEAT_MS) return;
    lastBeatAt.current = Date.now();
    void liveRecordingsService
      .upsert({
        boat_id: active.boatId,
        activity_id: active.activityId,
        client_recording_id: active.id,
      })
      .catch(() => {});
  }, [on, active, recordings]);

  // Stop advertising. Keyed on "there is no active recording any more" rather
  // than on the stop handler, so it also covers the app being reopened after
  // a recording died with its process.
  useEffect(() => {
    if (active || !announced.current) return;
    const { boatId } = announced.current;
    announced.current = null;
    lastBeatAt.current = 0;
    void liveRecordingsService.end(boatId).catch(() => {});
  }, [active]);
}
