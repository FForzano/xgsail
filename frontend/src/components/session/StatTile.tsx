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

/** `wide` halves the column count (2-up at every width) for a row of two or
 * four tiles whose values carry a second line — opt-in, so the default 4-up /
 * 2-up rhythm the playback and health readouts rely on is untouched. */
export function StatTiles({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  return <div className={wide ? `${styles.tiles} ${styles.wide}` : styles.tiles}>{children}</div>;
}
