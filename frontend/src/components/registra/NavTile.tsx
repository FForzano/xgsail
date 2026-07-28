import type { ReactNode } from "react";
import styles from "./NavModeOverlay.module.css";

export type NavTileTone = "default" | "port" | "starboard" | "warn";

/** The single metric primitive of the navigation display — every number on
 * that screen (SOG, COG, VMG, wind, distance, elapsed) renders through this,
 * so there is one place that decides how a reading looks.
 *
 * `hero` is the one oversized reading at any moment: SOG normally, the
 * countdown once the start timer is armed. */
export function NavTile({
  label,
  value,
  unit,
  hint,
  size = "normal",
  tone = "default",
  stale = false,
}: {
  label: string;
  value: string;
  unit?: string;
  hint?: ReactNode;
  size?: "hero" | "normal";
  tone?: NavTileTone;
  stale?: boolean;
}) {
  const classes = [
    styles.tile,
    size === "hero" ? styles.tileHero : "",
    tone !== "default" ? styles[`tone${tone[0].toUpperCase()}${tone.slice(1)}`] : "",
    stale ? styles.tileStale : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes}>
      <span className={styles.tileLabel}>{label}</span>
      <span className={styles.tileValue}>
        {value}
        {unit && <span className={styles.tileUnit}>{unit}</span>}
      </span>
      {hint && <span className={styles.tileHint}>{hint}</span>}
    </div>
  );
}
