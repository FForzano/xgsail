import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Capacitor } from "@capacitor/core";
import { Network } from "@capacitor/network";
import { Disc, Pause, Play, Square } from "lucide-react";
import { boatsService, boatKeys } from "@/services/boats";
import { activitiesService, activityKeys } from "@/services/activities";
import { sessionsService } from "@/services/sessions";
import { useImportUpload } from "@/hooks/useImportUpload";
import { useAuth } from "@/hooks/useAuth";
import * as nativeRecording from "@/services/nativeRecording";
import { ERROR_LOCATION_SERVICES_DISABLED, ERROR_PERMISSION_DENIED } from "@/services/nativeRecording";
import type { RecordingMeta } from "@/services/nativeRecording";
import { activityDisplayName } from "@/utils/activityName";
import { fmtDuration } from "@/utils/format";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import type { UUID } from "@/types";

const STANDALONE = "" as const; // empty select value = "uscita singola"

function ActivityPicker({
  id,
  value,
  onChange,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
}) {
  const { t } = useTranslation();
  const activities = useQuery({
    queryKey: activityKeys.list({ mine: "true" }),
    queryFn: () => activitiesService.list({ mine: true }),
  });
  return (
    <Select label={t("registra.linkTo")} id={id} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value={STANDALONE}>{t("registra.standalone")}</option>
      {activities.data?.map((a) => (
        <option key={a.id} value={a.id}>
          {activityDisplayName(a, t)}
        </option>
      ))}
    </Select>
  );
}

function elapsedLabel(startedAt: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000));
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Maps the sentinel error values nativeRecording.ts sets for a
 * permission/GPS failure to a translated message — everything else (upload
 * failures) is a raw, already-human-readable Error message and is shown as-is. */
function recordingErrorMessage(t: (key: string) => string, error: string | null | undefined): string | null {
  if (!error) return null;
  if (error === ERROR_PERMISSION_DENIED) return t("registra.error.permissionDenied");
  if (error === ERROR_LOCATION_SERVICES_DISABLED) return t("registra.error.locationServicesDisabled");
  return error;
}

/** Blocking popup for a GPS permission/location-services failure at start —
 * replaces silently falling back to inline red text, since by the time
 * that text renders nativeRecording.start() has already thrown and no
 * local recording was created (see nativeRecording.ts's GPS check). */
function GpsErrorModal({ error, onClose }: { error: string; onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <Modal title={t("registra.error.title")} onClose={onClose}>
      <p>{recordingErrorMessage(t, error)}</p>
      <div className="sf-form__actions">
        <Button variant="ghost" onClick={onClose}>
          {t("common.close")}
        </Button>
        {error === ERROR_PERMISSION_DENIED && (
          <Button
            onClick={() => {
              void nativeRecording.openSettings();
              onClose();
            }}
          >
            {t("registra.openSettings")}
          </Button>
        )}
      </div>
    </Modal>
  );
}

function durationSeconds(recording: RecordingMeta): number {
  const end = recording.endedAt ? new Date(recording.endedAt).getTime() : Date.now();
  return Math.max(0, Math.round((end - new Date(recording.startedAt).getTime()) / 1000));
}

/** Every Registra recording is the current user's own on-phone GPS trace,
 * so it always authorizes as a self-crew import (backend/routers/imports.py
 * `is_self_crew`) rather than requiring boat owner/admin — works whether or
 * not the recording user happens to also manage the boat. */
async function uploadRecording(
  recording: RecordingMeta,
  upload: ReturnType<typeof useImportUpload>,
  userId: UUID,
): Promise<{ error: string | null }> {
  try {
    await nativeRecording.setStatus(recording.id, "uploading");
    const file = await nativeRecording.readRecordingGpx(recording.id);
    const completed = await upload.start(file, {
      boatId: recording.boatId,
      activityId: recording.activityId ?? undefined,
      subjectType: "crew_member",
      subjectUserId: userId,
    });
    await nativeRecording.setStatus(recording.id, "uploaded", completed.session_id ?? undefined);
    // Once the backend confirms the import, the local copy (raw log + GPX)
    // has no further purpose — drop it instead of leaving it in the list.
    await nativeRecording.remove(recording.id);
    return { error: null };
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    // Persisted on the recording itself (not just returned) so a failure
    // triggered automatically after stop — with no caller around to show a
    // local error state — is still visible once it lands in the list.
    await nativeRecording.setStatus(recording.id, "failed", undefined, message);
    return { error: message };
  }
}

function RecordingRow({
  recording,
  online,
  onChanged,
}: {
  recording: RecordingMeta;
  online: boolean;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [activityId, setActivityId] = useState(recording.activityId ?? STANDALONE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const upload = useImportUpload();

  const boats = useQuery({ queryKey: boatKeys.mine, queryFn: () => boatsService.list(true) });
  const boatName = boats.data?.find((b) => b.id === recording.boatId)?.name ?? recording.boatId;

  const doUpload = async () => {
    if (!user) return;
    setBusy(true);
    setError(null);
    const { error } = await uploadRecording(recording, upload, user.id);
    setError(error);
    setBusy(false);
    onChanged();
  };

  const doReassign = async () => {
    setBusy(true);
    setError(null);
    try {
      if (recording.sessionId && activityId) {
        // Already uploaded: move the standalone session server-side.
        await sessionsService.attachToActivity(recording.sessionId, activityId as UUID);
      }
      await nativeRecording.setActivity(recording.id, activityId ? (activityId as UUID) : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      onChanged();
    }
  };

  const doRemove = async () => {
    await nativeRecording.remove(recording.id);
    onChanged();
  };

  return (
    <Card>
      <p className="sf-field__label">
        {new Date(recording.startedAt).toLocaleString()} — {boatName}
      </p>
      <p className="sf-muted">
        {!online && (recording.status === "stopped" || recording.status === "failed")
          ? t("registra.status.waitingNetwork")
          : t(`registra.status.${recording.status}`)}{" "}
        · {fmtDuration(durationSeconds(recording))}
      </p>
      <ActivityPicker id={`activity-${recording.id}`} value={activityId} onChange={setActivityId} />
      <div className="sf-form__actions">
        {(recording.status === "stopped" || recording.status === "failed") && (
          <Button onClick={() => void doUpload()} disabled={busy}>
            {t("registra.upload")}
          </Button>
        )}
        {activityId !== (recording.activityId ?? STANDALONE) && (
          <Button variant="ghost" onClick={() => void doReassign()} disabled={busy}>
            {t("registra.reassign")}
          </Button>
        )}
        {recording.status !== "recording" && recording.status !== "paused" && recording.status !== "uploading" && (
          <Button variant="danger" onClick={() => void doRemove()} disabled={busy}>
            {t("common.delete")}
          </Button>
        )}
        {recording.error === ERROR_PERMISSION_DENIED && (
          <Button variant="ghost" onClick={() => void nativeRecording.openSettings()}>
            {t("registra.openSettings")}
          </Button>
        )}
      </div>
      {(error ?? recordingErrorMessage(t, recording.error)) && (
        <p className="sf-form__error">{error ?? recordingErrorMessage(t, recording.error)}</p>
      )}
    </Card>
  );
}

export function RegistraPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { recordings, refresh } = nativeRecording.useRecordings();
  const [boatId, setBoatId] = useState("");
  const [activityId, setActivityId] = useState<string>(STANDALONE);
  const [activeId, setActiveId] = useState<UUID | null>(nativeRecording.activeRecordingId());
  const [error, setError] = useState<string | null>(null);
  const [, setTick] = useState(0);
  const [online, setOnline] = useState(true);
  const upload = useImportUpload();

  const boats = useQuery({ queryKey: boatKeys.mine, queryFn: () => boatsService.list(true) });

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Refs so attemptUpload/retryPending below stay referentially stable
  // (upload/user are fresh objects every render) — otherwise the retry
  // effect further down would tear down and re-subscribe its network
  // listener/interval on every render instead of once.
  const uploadRef = useRef(upload);
  uploadRef.current = upload;
  const userRef = useRef(user);
  userRef.current = user;
  const recordingsRef = useRef(recordings);
  recordingsRef.current = recordings;
  const uploadingIds = useRef<Set<UUID>>(new Set());

  const attemptUpload = useCallback(
    async (recording: RecordingMeta) => {
      const currentUser = userRef.current;
      if (!currentUser || uploadingIds.current.has(recording.id)) return;
      uploadingIds.current.add(recording.id);
      try {
        await uploadRecording(recording, uploadRef.current, currentUser.id);
      } finally {
        uploadingIds.current.delete(recording.id);
        refresh();
      }
    },
    [refresh],
  );

  const retryPending = useCallback(() => {
    recordingsRef.current
      .filter((r) => r.status === "stopped" || r.status === "failed")
      .forEach((r) => void attemptUpload(r));
  }, [attemptUpload]);

  // A recording made offline (e.g. airplane mode) sits as "stopped"/"failed"
  // until upload succeeds — retry as soon as connectivity returns, plus a
  // periodic fallback while this page is open (covers "connected but no
  // internet" cases the network-status event can miss). This only retries
  // while the app is in the foreground; a recording left pending with the
  // app fully closed needs the app reopened to finish uploading.
  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;
    Network.getStatus().then((status) => setOnline(status.connected));
    const networkSub = Network.addListener("networkStatusChange", (status) => {
      setOnline(status.connected);
      if (status.connected) retryPending();
    });
    const interval = window.setInterval(retryPending, 30_000);
    return () => {
      void networkSub.then((h) => h.remove());
      window.clearInterval(interval);
    };
  }, [retryPending]);

  // Live-updating elapsed-time display while a recording is running.
  useEffect(() => {
    if (!activeId) return;
    const id = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [activeId]);

  const activeEntry = recordings.find((r) => r.id === activeId);
  // A permission/GPS failure (see nativeRecording.ts's addWatcherFor) flips
  // the active recording's status to "failed" asynchronously, well after
  // onStart already resolved successfully — this effect is what notices it
  // and falls back to the start form with the error shown, instead of
  // leaving the recording controls displayed for a track that stopped
  // receiving any GPS fixes.
  useEffect(() => {
    if (activeEntry?.status === "permission_error" && activeId) {
      setError(activeEntry.error ?? null);
      setActiveId(null);
    }
  }, [activeEntry?.status, activeEntry?.error, activeId]);
  const active = activeEntry?.status === "recording" || activeEntry?.status === "paused" ? activeEntry : undefined;

  const onStart = async () => {
    setError(null);
    try {
      const id = await nativeRecording.start(boatId as UUID, activityId ? (activityId as UUID) : null);
      setActiveId(id);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onPause = async () => {
    await nativeRecording.pause();
    refresh();
  };

  const onResume = async () => {
    await nativeRecording.resume();
    refresh();
  };

  const onStop = async () => {
    const stopped = active;
    await nativeRecording.stop();
    setActiveId(null);
    refresh();
    // Upload happens automatically, no confirmation step — a failure (e.g.
    // no connectivity) still lands as "Caricamento fallito" and gets picked
    // up again by the retry effect above once the connection returns.
    if (stopped) void attemptUpload(stopped);
  };

  return (
    <>
      <Card title={t("registra.title")}>
        {active ? (
          <>
            <p className="sf-badge sf-badge--success">
              {t(active.status === "paused" ? "registra.status.paused" : "registra.recording")}
            </p>
            <p className="sf-field__label">{elapsedLabel(active.startedAt)}</p>
            <div className="sf-form__actions">
              {active.status === "paused" ? (
                <Button className="sf-btn--icon" onClick={() => void onResume()} aria-label={t("registra.resume")}>
                  <Play size={22} strokeWidth={1.75} />
                </Button>
              ) : (
                <Button
                  className="sf-btn--icon"
                  variant="ghost"
                  onClick={() => void onPause()}
                  aria-label={t("registra.pause")}
                >
                  <Pause size={22} strokeWidth={1.75} />
                </Button>
              )}
              <Button
                className="sf-btn--icon"
                variant="danger"
                onClick={() => void onStop()}
                aria-label={t("registra.stop")}
              >
                <Square size={22} strokeWidth={1.75} />
              </Button>
            </div>
          </>
        ) : (
          <>
            <Select
              label={t("sessions.importBoat")}
              id="registra-boat"
              value={boatId}
              onChange={(e) => setBoatId(e.target.value)}
              required
            >
              <option value="" disabled>
                …
              </option>
              {boats.data?.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
            <ActivityPicker id="registra-activity" value={activityId} onChange={setActivityId} />
            <div className="sf-form__actions">
              <Button
                className="sf-btn--icon"
                onClick={() => void onStart()}
                disabled={!boatId}
                aria-label={t("registra.start")}
              >
                <Disc size={22} strokeWidth={1.75} />
              </Button>
            </div>
            <p className="sf-muted">{t("registra.batteryHint")}</p>
            {error && error !== ERROR_PERMISSION_DENIED && error !== ERROR_LOCATION_SERVICES_DISABLED && (
              <p className="sf-form__error">{recordingErrorMessage(t, error)}</p>
            )}
          </>
        )}
      </Card>
      {(error === ERROR_PERMISSION_DENIED || error === ERROR_LOCATION_SERVICES_DISABLED) && (
        <GpsErrorModal error={error} onClose={() => setError(null)} />
      )}
      {recordings
        .filter((r) => r.id !== activeId)
        .map((r) => (
          <RecordingRow key={r.id} recording={r} online={online} onChanged={refresh} />
        ))}
      {recordings.length === 0 && !active && <p className="sf-muted">{t("registra.empty")}</p>}
    </>
  );
}
