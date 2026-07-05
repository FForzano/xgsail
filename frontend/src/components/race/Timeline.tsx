import { timeController, useTimeState } from "@/stores/timeController";
import { fmtTime } from "@/utils/format";

const SPEEDS = [1, 2, 4, 8];

// Transport bar: play/pause, speed multipliers, a scrub range, and the clock.
export function Timeline() {
  const { tMin, tMax, cursor, playing, speed } = useTimeState();

  return (
    <div className="sf-timeline">
      <button
        className="sf-btn sf-btn--primary sf-btn--sm"
        onClick={() => timeController.toggle()}
        aria-label={playing ? "Pause" : "Play"}
      >
        {playing ? "⏸" : "▶"}
      </button>
      <div className="sf-timeline__speeds">
        {SPEEDS.map((s) => (
          <button
            key={s}
            className={`sf-timeline__speed ${speed === s ? "active" : ""}`}
            onClick={() => timeController.setSpeed(s)}
          >
            {s}×
          </button>
        ))}
      </div>
      <input
        type="range"
        min={tMin}
        max={tMax}
        value={cursor}
        step={100}
        onChange={(e) => timeController.seek(Number(e.target.value))}
      />
      <span className="sf-timeline__clock">{tMax > tMin ? fmtTime(cursor) : "--:--:--"}</span>
    </div>
  );
}
