import type { ReactNode } from "react";
import styles from "./Notice.module.css";

/** A short, plain statement in place of content that isn't there: what is
 * happening, what it means for this page, and the one action that helps (if
 * the reader may take it). No box and no status colour — it is information,
 * not an alarm. `live` announces it to screen readers, for a state that
 * resolves on its own (something being prepared, a connection coming back). */
export function Notice({
  title,
  body,
  action,
  live = false,
}: {
  title: ReactNode;
  body?: ReactNode;
  action?: ReactNode;
  live?: boolean;
}) {
  return (
    <div className={styles.notice} role={live ? "status" : undefined}>
      <p className={styles.title}>{title}</p>
      {body && <p className={`sf-muted ${styles.body}`}>{body}</p>}
      {action && <div>{action}</div>}
    </div>
  );
}
