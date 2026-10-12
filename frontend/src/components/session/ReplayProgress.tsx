import { useRef, type KeyboardEvent, type PointerEvent } from "react";
import { timeController, useTimeState } from "@/stores/timeController";
import { fmtTime } from "@/utils/format";
import styles from "./ReplayProgress.module.css";

const clamp01 = (x: number) => Math.min(1, Math.max(0, x));

/** The speed strip folded down to a slim progress bar: the played part, the
 * position, and the numbered losses as ticks. A real slider — tap or drag to
 * seek, arrow keys to step — with a hit area far taller than the bar. */
export function ReplayProgress({
  markers,
  stepMs,
  label,
}: {
  markers: Array<{ ms: number; label: string }>;
  stepMs: number;
  label: string;
}) {
  const { tMin, tMax, cursor } = useTimeState();
  const ref = useRef<HTMLDivElement>(null);
  const span = tMax - tMin;
  const at = (ms: number) => `${(span > 0 ? clamp01((ms - tMin) / span) : 0) * 100}%`;

  const seekAt = (clientX: number) => {
    const r = ref.current?.getBoundingClientRect();
    if (!r || r.width <= 0 || span <= 0) return;
    timeController.seek(tMin + clamp01((clientX - r.left) / r.width) * span);
  };
  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    seekAt(e.clientX);
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) seekAt(e.clientX);
  };
  const onKeyDown = (e: KeyboardEvent) => {
    const step = { ArrowLeft: -stepMs, ArrowDown: -stepMs, ArrowRight: stepMs, ArrowUp: stepMs }[e.key];
    if (step != null) timeController.step(step);
    else if (e.key === "Home") timeController.seek(tMin);
    else if (e.key === "End") timeController.seek(tMax);
    else return;
    e.preventDefault();
  };

  return (
    <div
      ref={ref}
      className={styles.hit}
      role="slider"
      tabIndex={0}
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={span > 0 ? Math.round(clamp01((cursor - tMin) / span) * 100) : 0}
      aria-valuetext={span > 0 ? fmtTime(cursor) : undefined}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onKeyDown={onKeyDown}
    >
      <div className={styles.track}>
        <div className={styles.played} style={{ width: at(cursor) }} />
        {markers.map((m) => (
          <span key={m.label} className={styles.tick} style={{ left: at(m.ms) }} />
        ))}
        <span className={styles.thumb} style={{ left: at(cursor) }} />
      </div>
    </div>
  );
}
