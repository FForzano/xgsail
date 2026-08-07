import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Capacitor } from "@capacitor/core";
import { App as CapacitorApp } from "@capacitor/app";
import type { PluginListenerHandle } from "@capacitor/core";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import { useVisualViewportHeight } from "@/hooks/useVisualViewportHeight";
import styles from "./Modal.module.css";

let modalSeq = 0;
const openModals = new Set<number>();

// Minimal accessible modal: Esc closes, backdrop click closes, body content
// is arbitrary. Feature forms live inside as children.
export function Modal({
  title,
  onClose,
  size = "default",
  headerActions,
  footer,
  fillBody,
  children,
}: {
  title: ReactNode;
  onClose: () => void;
  size?: "default" | "wide";
  /** Icon-sized actions sitting next to the close button. For a `fillBody`
   * modal this is the only place an action can go without stealing height
   * from the editor filling the body. */
  headerActions?: ReactNode;
  footer?: ReactNode;
  /** Makes `.body` a flex column so a single `flex: 1` child (a `RichTextField`
   * with `fill`) can stretch to the modal's full remaining height, instead of
   * every field just taking its own content height. */
  fillBody?: boolean;
  children: ReactNode;
}) {
  // Assigned during render, not in an effect: parents render before children,
  // so a nested modal always outranks its opener — effects run child-first.
  const [depth] = useState(() => ++modalSeq);

  useEffect(() => {
    openModals.add(depth);
    return () => {
      openModals.delete(depth);
    };
  }, [depth]);

  const isTopmost = useCallback(() => depth === Math.max(...openModals), [depth]);

  const closeIfTopmost = useCallback(() => {
    if (isTopmost()) onClose();
  }, [isTopmost, onClose]);

  useEscapeKey(closeIfTopmost);
  useVisualViewportHeight();

  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;

    const listener = CapacitorApp.addListener("backButton", () => {
      closeIfTopmost();
    });

    return () => {
      void listener.then((h: PluginListenerHandle) => h.remove());
    };
  }, [closeIfTopmost]);

  return (
    <div
      className={`sf-modal__backdrop ${styles.backdrop} ${size === "wide" ? styles.backdropWide : ""}`}
      onClick={onClose}
    >
      <div
        className={`${styles.modal} ${size === "wide" ? styles.modalWide : ""}`}
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.head}>
          <h2 className={styles.title}>{title}</h2>
          <div className={styles.headActions}>
            {headerActions}
            <button className={styles.close} onClick={onClose} aria-label="Close">
              ×
            </button>
          </div>
        </div>
        <div className={`${styles.body} ${fillBody ? styles.bodyFill : ""}`}>{children}</div>
        {footer && <div className={styles.foot}>{footer}</div>}
      </div>
    </div>
  );
}
