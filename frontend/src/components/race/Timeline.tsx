import { useTranslation } from "react-i18next";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { timeController, useTimeState } from "@/stores/timeController";
import { fmtTime } from "@/utils/format";
import styles from "./Timeline.module.css";

// Compact transport bar: step back, play/pause, step forward, a speed-cycle
// button, and the clock. The speed chart itself is the scrubber (drag/tap to
// seek) — no separate progress bar, so this row stays narrow on mobile.
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
        className="sf-btn sf-btn--ghost sf-btn--sm"
        onClick={() => timeController.step(-stepMs)}
        aria-label={t("playback.stepBack")}
      >
        <SkipBack size={16} fill="currentColor" />
      </button>
      <button
        className="sf-btn sf-btn--primary sf-btn--sm"
        onClick={() => timeController.toggle()}
        aria-label={playing ? t("playback.pause") : t("playback.play")}
      >
        {playing ? <Pause size={16} fill="currentColor" /> : <Play size={16} fill="currentColor" />}
      </button>
      <button
        className="sf-btn sf-btn--ghost sf-btn--sm"
        onClick={() => timeController.step(stepMs)}
        aria-label={t("playback.stepForward")}
      >
        <SkipForward size={16} fill="currentColor" />
      </button>
      <button
        className={`sf-btn sf-btn--ghost sf-btn--sm ${styles.speed}`}
        onClick={() => timeController.cycleSpeed()}
        aria-label={t("playback.speed", { speed })}
      >
        {speed}×
      </button>
      <span className={styles.clock}>{tMax > tMin ? fmtTime(cursor) : "--:--:--"}</span>
    </div>
  );
}
