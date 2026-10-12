import { useTranslation } from "react-i18next";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { timeController, useTimeState } from "@/stores/timeController";
import { fmtTime } from "@/utils/format";
import styles from "./Timeline.module.css";

// Compact transport pill: step back, play/pause, step forward, a speed-cycle
// button, and the clock. The speed chart itself is the scrubber (drag/tap to
// seek) — no separate progress bar, so the pill stays small over the map.
// Its own buttons rather than `sf-btn`: the app's touch rule sizes every
// `sf-btn` box to 44px, which made the pill cover a phone map; here the
// boxes stay small and only the hit area is touch-sized (see the CSS).
export function Timeline({
  stepMs = 5000,
  overlay = false,
}: {
  stepMs?: number;
  /** Floats the bar on top of the map (see MapView's `controls` prop) instead
   * of its plain inline look. */
  overlay?: boolean;
}) {
  const { t } = useTranslation();
  const { tMin, tMax, cursor, playing, speed } = useTimeState();

  return (
    <div className={`${styles.timeline} ${overlay ? styles.overlay : ""}`}>
      <button
        type="button"
        className={styles.btn}
        onClick={() => timeController.step(-stepMs)}
        aria-label={t("playback.stepBack")}
      >
        <SkipBack size={15} fill="currentColor" aria-hidden />
      </button>
      <button
        type="button"
        className={`${styles.btn} ${styles.play}`}
        onClick={() => timeController.toggle()}
        aria-label={playing ? t("playback.pause") : t("playback.play")}
      >
        {playing ? <Pause size={15} fill="currentColor" aria-hidden /> : <Play size={15} fill="currentColor" aria-hidden />}
      </button>
      <button
        type="button"
        className={styles.btn}
        onClick={() => timeController.step(stepMs)}
        aria-label={t("playback.stepForward")}
      >
        <SkipForward size={15} fill="currentColor" aria-hidden />
      </button>
      <button
        type="button"
        className={`${styles.btn} ${styles.speed}`}
        onClick={() => timeController.cycleSpeed()}
        aria-label={t("playback.speed", { speed })}
      >
        {speed}×
      </button>
      <span className={styles.clock}>{tMax > tMin ? fmtTime(cursor) : "--:--:--"}</span>
    </div>
  );
}
