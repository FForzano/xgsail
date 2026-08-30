import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Capacitor } from "@capacitor/core";
import { Network } from "@capacitor/network";
import { App as CapacitorApp } from "@capacitor/app";
import { Disc, Gauge, Pause, Play, Square } from "lucide-react";
import { boatsService, boatKeys, cachedMyBoats, lastBoatId, rememberLastBoatId } from "@/services/boats";
import { GuestBoatDialog } from "@/components/common/GuestBoatDialog";
import { activitiesService, activityKeys } from "@/services/activities";
import { sessionsService } from "@/services/sessions";
import { useImportUpload } from "@/hooks/useImportUpload";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import * as nativeRecording from "@/services/nativeRecording";
import { ERROR_LOCATION_SERVICES_DISABLED, ERROR_PERMISSION_DENIED } from "@/services/nativeRecording";
import type { RecordingMeta } from "@/services/nativeRecording";
import { activityDisplayName } from "@/utils/activityName";
import { fmtDuration, userLabel } from "@/utils/format";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { BottomSheet } from "@/components/ui/BottomSheet";
import { Spinner } from "@/components/ui/Spinner";
import { devicesService, deviceKeys, XGSAIL_E1_PARSER_KEY } from "@/services/devices";
import { useE1Device } from "@/hooks/useE1Device";
import { NavModeOverlay } from "@/components/registra/NavModeOverlay";
import { LiveRecordingBanner } from "@/components/diario/LiveRecordingBanner";
import type { JoinRecordingState } from "@/components/diario/LiveRecordingBanner";
import { ExplorerMap } from "@/components/map/ExplorerMap";
import { useOnboarding } from "@/onboarding/OnboardingContext";
import type { Device, UUID } from "@/types";
import styles from "./RegistraPage.module.css";

const STANDALONE = "" as const; // empty select value = "uscita singola"
const PHONE_SOURCE = "phone" as const; // recording source select: this phone's own GPS
const GUEST_BOAT_SENTINEL = "__guest__" as const; // boat select: "add a guest boat" option

function ActivityPicker({
  id,
  value,
  onChange,
  disabled,
  dataTour,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  dataTour?: string;
}) {
  const { t } = useTranslation();
  const activities = useQuery({
    queryKey: activityKeys.list({ mine: "true" }),
    queryFn: () => activitiesService.list({ mine: true }),
  });
  // Races the sailor's boats are entered for. Kept as a separate query (and a
  // separate group below) because it answers a different question from "my
  // activities": these belong to the organizing club, not to the sailor, and
  // are reachable through the regatta's start list rather than ownership.
  const races = useQuery({
    queryKey: activityKeys.list({ entered: "true" }),
    queryFn: () => activitiesService.list({ entered: true }),
  });
  return (
    <Select
      label={t("registra.linkTo")}
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      data-tour={dataTour}
    >
      <option value={STANDALONE}>{t("registra.standalone")}</option>
      {races.data && races.data.length > 0 && (
        <optgroup label={t("registra.myRaces")}>
          {races.data.map((a) => (
            <option key={a.id} value={a.id}>
              {activityDisplayName(a, t)}
            </option>
          ))}
        </optgroup>
      )}
      {activities.data && activities.data.length > 0 && (
        <optgroup label={t("registra.myActivities")}>
          {activities.data.map((a) => (
            <option key={a.id} value={a.id}>
              {activityDisplayName(a, t)}
            </option>
          ))}
        </optgroup>
      )}
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

/** Dev-only: `/registra?navmock=1` opens the navigation display against a
 * synthetic GPS feed, so its layout, typography and sailing math can be
 * worked on in a desktop browser — there is no background-geolocation
 * watcher off native, and normally no way to reach the overlay at all.
 * `import.meta.env.DEV` is a build-time constant, so this and the mock module
 * behind it are absent from production builds. */
function useNavMockRecording(): RecordingMeta | null {
  const [recording, setRecording] = useState<RecordingMeta | null>(null);

  useEffect(() => {
    if (!import.meta.env.DEV) return;
    if (!new URLSearchParams(window.location.search).has("navmock")) return;
    let stop: (() => void) | null = null;
    void import("@/services/liveFixMock").then((mock) => {
      mock.startMockFixes();
      stop = mock.stopMockFixes;
      setRecording({
        id: "navmock" as UUID,
        boatId: "navmock" as UUID,
        activityId: null,
        startedAt: new Date().toISOString(),
        endedAt: null,
        status: "recording",
        pointCount: 0,
      });
    });
    return () => stop?.();
  }, []);

  return recording;
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
  onMerged?: (crewNames: string[]) => void,
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
    if (completed.session_merged) {
      // The backend joined this track to an outing that was already there.
      // Opportunistic only — an upload often completes with the app in the
      // background, and the local row is about to be deleted either way, so
      // the durable place to notice (and to undo it) is the session's own
      // track menu, not here.
      onMerged?.(completed.session_crew.map(userLabel));
    }
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
  const { notify } = useToast();
  const [activityId, setActivityId] = useState(recording.activityId ?? STANDALONE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const upload = useImportUpload();

  const boats = useQuery({
    queryKey: boatKeys.mine,
    queryFn: () => boatsService.list(true),
    initialData: () => cachedMyBoats() ?? undefined,
    // The cache is a fallback, not fresh data: refetch immediately when online.
    initialDataUpdatedAt: 0,
  });
  const boatName = boats.data?.find((b) => b.id === recording.boatId)?.name ?? recording.boatId;

  const doUpload = async () => {
    if (!user) return;
    setBusy(true);
    setError(null);
    const { error } = await uploadRecording(recording, upload, user.id, (names) =>
      notify(t("sessions.navSource.mergedWith", { names: names.join(", ") }), "info"),
    );
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

  // An interrupted recording is uploadable only if some track was actually
  // captured before it died — an empty GPX would import as a pointless
  // session with nothing in it.
  const canUpload =
    recording.status === "stopped" ||
    recording.status === "failed" ||
    (recording.status === "interrupted" && recording.pointCount > 0);

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
      {recording.status === "interrupted" && (
        <p className="sf-muted">
          {t(recording.pointCount > 0 ? "registra.interruptedHint" : "registra.interruptedEmpty")}
        </p>
      )}
      <ActivityPicker id={`activity-${recording.id}`} value={activityId} onChange={setActivityId} />
      <div className="sf-form__actions">
        {canUpload && (
          <Button onClick={() => void doUpload()} disabled={busy}>
            {t("registra.upload")}
          </Button>
        )}
        {activityId !== (recording.activityId ?? STANDALONE) && (
          <Button variant="ghost" onClick={() => void doReassign()} disabled={busy}>
            {t("registra.reassign")}
          </Button>
        )}
        {/* Always offered: this list only ever renders recordings that are
            not the active one, so nothing here is a live track being
            recorded — a row stuck in a running-looking state (an app killed
            mid-recording, an upload interrupted) is exactly the case that
            most needs a way out. `busy` covers an operation this row itself
            started. */}
        <Button variant="danger" onClick={() => void doRemove()} disabled={busy}>
          {t("common.delete")}
        </Button>
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

/** Start/stop controls for an XGSail E1 chosen as the recording source
 * (instead of this phone's own GPS). Connection state, `recording.logging`
 * and `pending_uploads` all come straight from the device's `status`
 * characteristic (xgsail-e1's docs/ble-config.md) — the device is the
 * source of truth here, there's no separate local recording state to keep
 * in sync. `boatId`/`activityId` are forwarded to `start-rec`, same fields
 * `session-uploads` already accepts either way the session is eventually
 * uploaded (WiFi or BLE relay). */
function E1RecordingControl({
  device,
  boatId,
  activityId,
}: {
  device: Device;
  boatId: string;
  activityId: string;
}) {
  const { t } = useTranslation();
  const e1 = useE1Device(device);

  if (e1.state === "searching") {
    return (
      <>
        <Spinner />
        <p className="sf-muted">{t("devices.e1.searching")}</p>
      </>
    );
  }

  if (e1.state === "unreachable") {
    return (
      <>
        <p className="sf-muted">{t("devices.e1.unreachable")}</p>
        <div className="sf-form__actions">
          <Button variant="ghost" onClick={e1.retry}>
            {t("common.retry")}
          </Button>
        </div>
      </>
    );
  }

  const logging = e1.status?.recording.logging ?? false;
  const pending = e1.status?.recording.pending_uploads ?? 0;

  return (
    <>
      <p className={logging ? "sf-badge sf-badge--success" : "sf-muted"}>
        {logging
          ? `${t("registra.recording")} (${fmtDuration(e1.status?.recording.elapsed_s)})`
          : t("registra.source.e1Idle")}
      </p>
      {pending > 0 && <p className="sf-muted">{t("registra.source.pendingUploads", { count: pending })}</p>}
      <div className="sf-form__actions">
        {logging ? (
          <Button
            className="sf-btn--icon"
            variant="danger"
            onClick={() => e1.stopRec.mutate()}
            disabled={e1.stopRec.isPending}
            aria-label={t("registra.stop")}
          >
            <Square size={22} strokeWidth={1.75} />
          </Button>
        ) : (
          <Button
            className="sf-btn--icon"
            data-tour="registra-start"
            onClick={() =>
              e1.startRec.mutate({
                boatId: boatId ? (boatId as UUID) : undefined,
                activityId: activityId ? (activityId as UUID) : undefined,
              })
            }
            disabled={e1.startRec.isPending}
            aria-label={t("registra.start")}
          >
            <Disc size={22} strokeWidth={1.75} />
          </Button>
        )}
      </div>
    </>
  );
}

export function RegistraPage() {
  const { t } = useTranslation();
  const { user, identityStale } = useAuth();
  const { notify } = useToast();
  const { isDemoTarget } = useOnboarding();
  // Recording needs a background-geolocation foreground service, which only
  // exists in the native builds (see services/nativeRecording.ts). The web
  // build still gets this page for the exploration map, with the recording
  // controls visible but inert so it's clear what the app adds.
  const native = Capacitor.isNativePlatform();
  const { recordings, refresh } = nativeRecording.useRecordings();
  const [boatId, setBoatId] = useState("");
  const [activityId, setActivityId] = useState<string>(STANDALONE);
  const [source, setSource] = useState<string>(PHONE_SOURCE);
  const [activeId, setActiveId] = useState<UUID | null>(nativeRecording.activeRecordingId());
  const [error, setError] = useState<string | null>(null);
  const [, setTick] = useState(0);
  const [online, setOnline] = useState(true);
  const [navMode, setNavMode] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [guestDialogOpen, setGuestDialogOpen] = useState(false);
  const upload = useImportUpload();

  // initialData falls back to the last successfully cached "my boats" list
  // (written by boatsService.list on every online fetch) so the boat picker
  // still has options after an app restart in airplane mode — a plain fetch
  // failure otherwise clears TanStack's in-memory cache back to nothing.
  const boats = useQuery({
    queryKey: boatKeys.mine,
    queryFn: () => boatsService.list(true),
    initialData: () => cachedMyBoats() ?? undefined,
    // The cache is a fallback, not fresh data: refetch immediately when online.
    initialDataUpdatedAt: 0,
  });

  // Arriving from the "someone is recording — record too" banner: the whole
  // point is that both recordings name the same boat and activity, so the
  // choice is made here rather than left to the user to reproduce. Cleared
  // from history straight away so going back doesn't re-apply it.
  const location = useLocation();
  const navigate = useNavigate();
  const joinState = location.state as JoinRecordingState | null;
  useEffect(() => {
    if (!joinState?.prefillBoatId) return;
    setBoatId(joinState.prefillBoatId);
    setActivityId(joinState.prefillActivityId ?? STANDALONE);
    setSheetOpen(true);
    navigate(".", { replace: true, state: null });
  }, [joinState, navigate]);

  // The sheet is closed by default, so a tour step pointing at one of its
  // fields would find nothing to frame (same reasoning as isDemoTarget usage
  // in MyDiaryPage/UpcomingEventsBanner) — open it while such a step is
  // active. Never closes it back: the tour may still be on a step inside it.
  useEffect(() => {
    if (
      isDemoTarget("registra-fields") ||
      isDemoTarget("registra-boat") ||
      isDemoTarget("registra-activity") ||
      isDemoTarget("registra-start")
    ) {
      setSheetOpen(true);
    }
  }, [isDemoTarget]);

  // Preselect the last boat used to record, once the (possibly cached)
  // boat list is available and nothing has been chosen yet. Skipped when the
  // banner above already named a boat — that choice is the deliberate one.
  useEffect(() => {
    if (boatId || joinState?.prefillBoatId || !boats.data?.length) return;
    const last = lastBoatId();
    if (last && boats.data.some((b) => b.id === last)) setBoatId(last);
  }, [boats.data, boatId, joinState]);

  // XGSail E1 devices claimed by this user, available as a recording
  // source alongside the phone's own GPS — native only (BLE), same
  // eligibility check as useE1Device.
  const deviceTypes = useQuery({ queryKey: deviceKeys.types, queryFn: devicesService.listTypes });
  const devicesQuery = useQuery({
    queryKey: deviceKeys.all,
    queryFn: devicesService.list,
    enabled: native,
  });
  const e1Devices = (devicesQuery.data ?? []).filter(
    (d) =>
      d.status === "claimed" &&
      deviceTypes.data?.find((dt) => dt.id === d.device_type_id)?.parser_key === XGSAIL_E1_PARSER_KEY,
  );
  const selectedE1Device = source !== PHONE_SOURCE ? e1Devices.find((d) => d.id === source) : undefined;

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
        await uploadRecording(recording, uploadRef.current, currentUser.id, (names) =>
          notify(t("sessions.navSource.mergedWith", { names: names.join(", ") }), "info"),
        );
      } finally {
        uploadingIds.current.delete(recording.id);
        refresh();
      }
    },
    [refresh, notify, t],
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
  //
  // Suspended in navigation mode: each tick can kick off a multipart GPX
  // upload over cellular, the most expensive thing on this page, and nothing
  // in the backlog is urgent mid-race. It resumes on the way out — the
  // pending recordings are untouched meanwhile.
  useEffect(() => {
    if (!Capacitor.isNativePlatform() || navMode) return;
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
  }, [retryPending, navMode]);

  // Reopening the app (e.g. after airplane mode was turned off while it sat
  // in the background) is another moment connectivity may have come back
  // that the network-status event can miss — nudge the same retry, no new
  // upload logic here.
  useEffect(() => {
    if (!Capacitor.isNativePlatform() || navMode) return;
    const sub = CapacitorApp.addListener("appStateChange", ({ isActive }) => {
      if (isActive) retryPending();
    });
    return () => void sub.then((h) => h.remove());
  }, [retryPending, navMode]);

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
  const realActive =
    activeEntry?.status === "recording" || activeEntry?.status === "paused" ? activeEntry : undefined;
  const mockRecording = useNavMockRecording();
  const active = realActive ?? mockRecording ?? undefined;

  const onStart = async () => {
    setError(null);
    try {
      const id = await nativeRecording.start(boatId as UUID, activityId ? (activityId as UUID) : null);
      rememberLastBoatId(boatId as UUID);
      setActiveId(id);
      setSheetOpen(false);
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
    setNavMode(false);
    await nativeRecording.stop();
    setActiveId(null);
    refresh();
    // Upload happens automatically, no confirmation step — a failure (e.g.
    // no connectivity) still lands as "Caricamento fallito" and gets picked
    // up again by the retry effect above once the connection returns.
    if (stopped) void attemptUpload(stopped);
  };

  const pendingRecordingCount = recordings.filter(
    (r) =>
      r.id !== activeId &&
      (r.status === "stopped" ||
        r.status === "failed" ||
        r.status === "uploading" ||
        // Interrupted ones can only leave the list by the user's hand
        // (upload or delete), so they keep the badge until dealt with.
        r.status === "interrupted"),
  ).length;

  return (
    <div className={styles.page}>
      {/* Full-height map, always mounted */}
      <ExplorerMap fill className={styles.mapContainer} dataTour="registra-map" />

      {/* FAB: record button when idle */}
      {!active && (
        <button
          type="button"
          className={`sf-btn sf-btn--icon sf-btn--danger ${styles.fab}`}
          data-tour="registra-record"
          onClick={() => setSheetOpen(true)}
          aria-label={t("registra.start")}
        >
          <Disc size={24} strokeWidth={1.75} />
          {pendingRecordingCount > 0 && <span className="sf-nav-dot sf-nav-dot--floating" aria-hidden />}
        </button>
      )}

      {/* Status panel: floating controls during an active recording */}
      {active && (
        <div className={styles.statusPanel}>
          <p className="sf-badge sf-badge--success">
            {t(active.status === "paused" ? "registra.status.paused" : "registra.recording")}
          </p>
          <p style={{ margin: 0, fontSize: "1.25rem", fontWeight: 700 }}>
            {elapsedLabel(active.startedAt)}
          </p>
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
          <div className="sf-form__actions">
            <Button onClick={() => setNavMode(true)}>
              <Gauge size={18} strokeWidth={1.75} /> {t("registra.nav.enter")}
            </Button>
          </div>
        </div>
      )}

      {/* Bottom sheet: pre-recording form */}
      <BottomSheet open={sheetOpen && !active} onClose={() => setSheetOpen(false)} title={t("registra.title")}>
        <div data-tour="registra-fields">
          {e1Devices.length > 0 && (
            <Select
              label={t("registra.source.label")}
              id="registra-source"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            >
              <option value={PHONE_SOURCE}>{t("registra.source.phone")}</option>
              {e1Devices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.nickname ?? d.external_id ?? d.id.slice(0, 8)}
                </option>
              ))}
            </Select>
          )}
          {!native && <p className="sf-muted">{t("registra.webUnsupported")}</p>}
          {/* Last chance to notice somebody aboard is already recording, right
              where the boat is about to be chosen. */}
          <LiveRecordingBanner />
          <Select
            label={t("sessions.importBoat")}
            id="registra-boat"
            value={boatId}
            onChange={(e) => {
              if (e.target.value === GUEST_BOAT_SENTINEL) {
                setGuestDialogOpen(true);
                return;
              }
              setBoatId(e.target.value);
            }}
            required
            disabled={!native}
            data-tour="registra-boat"
          >
            <option value="" disabled>
              …
            </option>
            {boats.data?.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
            <option value={GUEST_BOAT_SENTINEL}>{t("boats.guestBoatOption")}</option>
          </Select>
          <ActivityPicker
            id="registra-activity"
            value={activityId}
            onChange={setActivityId}
            disabled={!native}
            dataTour="registra-activity"
          />
        </div>
        {native && (!online || identityStale) && (
          <p className="sf-badge sf-badge--warning">{t("registra.offlineWarning")}</p>
        )}
        {selectedE1Device ? (
          <E1RecordingControl device={selectedE1Device} boatId={boatId} activityId={activityId} />
        ) : (
          <>
            <div className="sf-form__actions">
              <Button
                className="sf-btn--icon"
                data-tour="registra-start"
                onClick={() => void onStart()}
                disabled={!native || !boatId}
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
        {/* Pending recordings list inside the sheet */}
        {recordings.filter((r) => r.id !== activeId).map((r) => (
          <RecordingRow key={r.id} recording={r} online={online} onChanged={refresh} />
        ))}
        {recordings.length === 0 && !active && <p className="sf-muted">{t("registra.empty")}</p>}
      </BottomSheet>

      {/* Navigation mode overlay */}
      {navMode && active && (
        <NavModeOverlay
          recording={active}
          onPause={() => void onPause()}
          onResume={() => void onResume()}
          onStop={() => void onStop()}
          onExit={() => setNavMode(false)}
        />
      )}

      {/* GPS error modal */}
      {(error === ERROR_PERMISSION_DENIED || error === ERROR_LOCATION_SERVICES_DISABLED) && (
        <GpsErrorModal error={error} onClose={() => setError(null)} />
      )}

      <GuestBoatDialog
        open={guestDialogOpen}
        onClose={() => setGuestDialogOpen(false)}
        onCreated={(boat) => {
          setBoatId(boat.id);
          setGuestDialogOpen(false);
        }}
      />
    </div>
  );
}
