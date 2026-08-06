import { useEffect, type ReactNode } from "react";
import { Capacitor } from "@capacitor/core";
import { App as CapacitorApp } from "@capacitor/app";
import type { PluginListenerHandle } from "@capacitor/core";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import { useVisualViewportHeight } from "@/hooks/useVisualViewportHeight";
import styles from "./Modal.module.css";

// Minimal accessible modal: Esc closes, backdrop click closes, body content
// is arbitrary. Feature forms live inside as children.
export function Modal({
  title,
  onClose,
  size = "default",
  footer,
  children,
}: {
  title: ReactNode;
  onClose: () => void;
  size?: "default" | "wide";
  footer?: ReactNode;
  children: ReactNode;
}) {
  useEscapeKey(onClose);
  useVisualViewportHeight();

  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;

    const listener = CapacitorApp.addListener("backButton", () => {
      onClose();
    });

    return () => {
      void listener.then((h: PluginListenerHandle) => h.remove());
    };
  }, [onClose]);

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
          <button className={styles.close} onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className={styles.body}>{children}</div>
        {footer && <div className={styles.foot}>{footer}</div>}
      </div>
    </div>
  );
}
