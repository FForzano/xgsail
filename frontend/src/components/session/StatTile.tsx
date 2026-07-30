import type { ReactNode } from "react";
import styles from "./statTiles.module.css";

// A labelled value, and a row of them. Used both for readouts that follow the
// playback cursor (PlaybackIndicators) and for session aggregates (HealthCard).
export function StatTile({ label, value }: { label: ReactNode; value: ReactNode }) {
  return (
    <div className={styles.tile}>
      <span className={styles.label}>{label}</span>
      <span className={styles.value}>{value}</span>
    </div>
  );
}

export function StatTiles({ children }: { children: ReactNode }) {
  return <div className={styles.tiles}>{children}</div>;
}
