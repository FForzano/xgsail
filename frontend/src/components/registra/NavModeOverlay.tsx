import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { focusManager } from "@tanstack/react-query";
import { Capacitor } from "@capacitor/core";
import { App as CapacitorApp } from "@capacitor/app";
import { BatteryCharging, BatteryWarning, Pause, Play, Square, X } from "lucide-react";
import { useNavInstruments } from "@/hooks/useNavInstruments";
import { useBatteryStatus } from "@/hooks/useBatteryStatus";
import { useUnits } from "@/stores/unitsStore";
import { navModeStore } from "@/stores/navModeStore";
import * as screenWakeLock from "@/services/screenWakeLock";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { fmtBearing, fmtDistance, fmtDuration, splitKnots } from "@/utils/format";
import type { RecordingMeta } from "@/services/nativeRecording";
import { NavStartTimer } from "./NavStartTimer";
import { NavTile } from "./NavTile";
import styles from "./NavModeOverlay.module.css";

// Sailing abbreviations (SOG, COG, VMG, TWA, TWD, TWS) are deliberately NOT
// translated: they're identical on every instrument in every market, and
// keying them would be churn for no reader's benefit. Only prose is i18n'd.

// Deliberate friction on the way out — this button sits on a screen that gets
// touched with wet hands on a moving boat, and an accidental exit drops the
// user back into the app mid-race.
const EXIT_HOLD_MS = 800;

// Dynamic, like main.tsx's own call: it keeps @capacitor/status-bar's native
// calls out of the web bundle's execution path (same convention as
// nativeAuth/nativeUpdater).
const setStatusBar = (on: boolean) =>
  void import("@/services/nativeStatusBar").then((m) => m.setNavModeStatusBar(on));

function elapsedSeconds(recording: RecordingMeta): number {
  return Math.max(0, Math.round((Date.now() - new Date(recording.startedAt).getTime()) / 1000));
}

/** Full-screen, true-black instrument display shown over the recording
 * screen. Rendered into `document.body` via a portal, which also puts it
 * outside AppShell's `<main>` — so the app's swipe-between-sections and
 * pull-to-refresh gestures can't fire from a touch in here at all.
 *
 * It owns no recording state: pause/resume/stop are the callbacks
 * RegistraPage already uses, passed straight through. */
export function NavModeOverlay({
  recording,
  onPause,
  onResume,
  onStop,
  onExit,
}: {
  recording: RecordingMeta;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onExit: () => void;
}) {
  const { t } = useTranslation();
  const instruments = useNavInstruments();
  const battery = useBatteryStatus();
  useUnits(); // re-render if the unit preference changes underneath us
  const [startsAt, setStartsAt] = useState<string | null>(null);
  const [confirmStop, setConfirmStop] = useState(false);
  const [wakeLockOk, setWakeLockOk] = useState(true);
  const [holding, setHolding] = useState(false);
  const holdTimer = useRef<number | null>(null);

  // Everything acquired here is released in the cleanup, not in `onExit` —
  // the overlay also unmounts on paths the user never triggers (a revoked
  // location permission nulls the active recording out from under it), and
  // every one of those must still restore the screen and the background work.
  useEffect(() => {
    navModeStore.set(true);
    setStatusBar(true);
    void screenWakeLock.acquire().then(setWakeLockOk);
    document.body.classList.add("sf-nav-mode");
    // Stop refetch-on-focus cascades for the duration: every avoided request
    // is a cellular radio that doesn't wake up. Deliberately NOT paired with
    // cancelQueries() — that would abort the wind lookup this display just
    // started, and `useWindAt` sets retry: false, so it would never come back.
    focusManager.setFocused(false);

    return () => {
      navModeStore.set(false);
      setStatusBar(false);
      void screenWakeLock.release();
      document.body.classList.remove("sf-nav-mode");
      // `undefined` restores default event-driven behaviour; `true` would
      // force an immediate global refetch storm on the way out.
      focusManager.setFocused(undefined);
    };
  }, []);

  const paused = recording.status === "paused";

  const exit = useCallback(() => {
    if (holdTimer.current != null) window.clearTimeout(holdTimer.current);
    setHolding(false);
    onExit();
  }, [onExit]);

  // Android's back button must not drop out of navigation mode by accident —
  // registering a listener at all is what suppresses the default navigation.
  // Native only: the App plugin has no backButton event on the web.
  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;
    const listener = CapacitorApp.addListener("backButton", () => {
      /* intentionally inert: exit is the hold-to-exit button only */
    });
    return () => {
      void listener.then((h) => h.remove());
    };
  }, []);

  // Esc is the desktop/dev escape hatch. Skipped while the stop confirmation
  // is open, where Esc belongs to the dialog.
  useEffect(() => {
    if (confirmStop) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") exit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirmStop, exit]);

  const startHold = () => {
    setHolding(true);
    holdTimer.current = window.setTimeout(exit, EXIT_HOLD_MS);
  };
  const cancelHold = () => {
    if (holdTimer.current != null) window.clearTimeout(holdTimer.current);
    holdTimer.current = null;
    setHolding(false);
  };
  useEffect(() => cancelHold, []);

  const lost = instruments.gpsQuality === "lost";
  const sog = splitKnots(instruments.sogKts);
  const tws = splitKnots(instruments.twsKts);
  const vmgSpeed = splitKnots(instruments.vmgKts == null ? null : Math.abs(instruments.vmgKts));
  const hasWind = instruments.twdDeg != null;
  // The start timer takes the hero slot once armed — the pre-start minutes are
  // the one time a countdown matters more than boat speed.
  const timerArmed = startsAt != null;
  const batteryPct = battery.level == null ? null : Math.round(battery.level * 100);
  const batteryLow = batteryPct != null && batteryPct <= 20 && !battery.charging;

  return createPortal(
    <div className={styles.root} role="dialog" aria-modal="true" aria-label={t("registra.nav.enter")}>
      <div className={styles.status}>
        <span className={`${styles.statusDot} ${styles[`gps${instruments.gpsQuality[0].toUpperCase()}${instruments.gpsQuality.slice(1)}`]}`} />
        <span>{t(`registra.nav.gps.${instruments.gpsQuality}`)}</span>
        {instruments.accuracyM != null && !lost && <span>±{Math.round(instruments.accuracyM)} m</span>}
        <span className={styles.statusRec}>
          {t(paused ? "registra.status.paused" : "registra.status.recording")}
        </span>
        {batteryPct != null && (
          <span className={`${styles.statusBattery} ${batteryLow ? styles.statusBatteryLow : ""}`}>
            {battery.charging ? <BatteryCharging size={16} /> : batteryLow ? <BatteryWarning size={16} /> : null}
            {batteryPct}%
          </span>
        )}
      </div>

      {!wakeLockOk && <p className={styles.warning}>{t("registra.nav.wakeLockUnavailable")}</p>}
      {/* The OS's own power saving can throttle background work and refuse
          the wake lock outright — surfacing it here beats the display
          looking silently broken with no explanation. */}
      {battery.lowPowerMode && <p className={styles.warning}>{t("registra.nav.lowPowerMode")}</p>}

      <div className={styles.hero}>
        {timerArmed ? (
          <NavStartTimer startsAt={startsAt} onChange={setStartsAt} />
        ) : (
          <NavTile label="SOG" value={sog.value} unit={sog.unit} size="hero" stale={lost} />
        )}
      </div>

      <div className={styles.grid}>
        {timerArmed && <NavTile label="SOG" value={sog.value} unit={sog.unit} stale={lost} />}
        <NavTile label="COG" value={fmtBearing(instruments.cogDeg)} stale={lost} />
        <NavTile label={t("registra.nav.distance")} value={fmtDistance(instruments.distanceM)} />
        <NavTile label={t("registra.nav.elapsed")} value={fmtDuration(elapsedSeconds(recording))} />
        <NavTile label={t("registra.nav.maxSpeed")} value={splitKnots(instruments.maxSogKts).value} unit={sog.unit} />
        <NavTile label={t("registra.nav.avgSpeed")} value={splitKnots(instruments.avgSogKts).value} unit={sog.unit} />

        {/* Wind and everything derived from it disappear entirely without
            coverage — four dashes would just be noise, and offshore that's
            the normal case, not a fault. */}
        {hasWind && (
          <>
            <NavTile
              label="TWD / TWS"
              value={`${fmtBearing(instruments.twdDeg)} · ${tws.value}`}
              unit={tws.unit}
              hint={
                <>
                  ≈ {t("registra.nav.wind.source", { source: instruments.windSource })}
                  {instruments.windAgeMin != null &&
                    ` · ${t("registra.nav.wind.age", { minutes: instruments.windAgeMin })}`}
                </>
              }
            />
            <NavTile
              label="TWA"
              value={instruments.twaDeg == null ? "—" : `${Math.abs(Math.round(instruments.twaDeg))}°`}
              tone={instruments.tack ?? "default"}
              hint={instruments.tack ? t(`registra.nav.tack.${instruments.tack}`) : undefined}
            />
            <NavTile
              label="VMG"
              value={
                instruments.vmgKts == null
                  ? "—"
                  : `${instruments.vmgKts >= 0 ? "▲" : "▼"} ${vmgSpeed.value}`
              }
              unit={vmgSpeed.unit}
            />
          </>
        )}
      </div>

      {!hasWind && <p className={styles.windNote}>{t("registra.nav.wind.unavailable")}</p>}
      {!timerArmed && <NavStartTimer startsAt={startsAt} onChange={setStartsAt} />}

      <div className={styles.controls}>
        <button
          type="button"
          className={`${styles.control} ${holding ? styles.controlHolding : ""}`}
          onPointerDown={startHold}
          onPointerUp={cancelHold}
          onPointerLeave={cancelHold}
          onPointerCancel={cancelHold}
          aria-label={t("registra.nav.exitHold")}
          title={t("registra.nav.exitHold")}
        >
          <X size={26} strokeWidth={1.75} />
        </button>
        <button
          type="button"
          className={styles.control}
          onClick={paused ? onResume : onPause}
          aria-label={t(paused ? "registra.resume" : "registra.pause")}
        >
          {paused ? <Play size={26} strokeWidth={1.75} /> : <Pause size={26} strokeWidth={1.75} />}
        </button>
        <button
          type="button"
          className={`${styles.control} ${styles.controlStop}`}
          onClick={() => setConfirmStop(true)}
          aria-label={t("registra.stop")}
        >
          <Square size={26} strokeWidth={1.75} />
        </button>
      </div>

      {confirmStop && (
        <ConfirmDialog
          title={t("registra.nav.stopConfirm.title")}
          message={t("registra.nav.stopConfirm.message")}
          confirmLabel={t("registra.stop")}
          onConfirm={() => {
            setConfirmStop(false);
            onStop();
          }}
          onClose={() => setConfirmStop(false)}
        />
      )}
    </div>,
    document.body,
  );
}
