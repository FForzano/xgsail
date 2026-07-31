import { Sailboat, Trophy } from "lucide-react";
import styles from "./MediaPlaceholder.module.css";

export type MediaKind = "regatta" | "activity";

const ICONS = { regatta: Trophy, activity: Sailboat } as const;

/** Kind-tinted placeholder for an event with no cover image, shared by the
 * diario feed card (`EventRow`) and the regatta hero. Absolutely positioned:
 * drop it inside a positioned box that already has the aspect ratio you
 * want. */
export function MediaPlaceholder({ kind, size = 32 }: { kind: MediaKind; size?: number }) {
  const Icon = ICONS[kind];
  return (
    <div className={styles.placeholder} data-kind={kind} aria-hidden>
      <Icon size={size} />
    </div>
  );
}
