import { useEffect } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { Capacitor } from "@capacitor/core";
import { App as CapacitorApp } from "@capacitor/app";
import type { PluginListenerHandle } from "@capacitor/core";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import styles from "./BottomSheet.module.css";

/** A bottom sheet that slides up from the bottom of the screen, portaled to
 * document.body so it sits above the app shell's gesture recognizers and
 * can be dismissed via backdrop click, Esc, or the native Android back button. */
export function BottomSheet({
  open,
  onClose,
  title,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  /** Rendered below the scrollable content, outside it — for a primary
   * action (e.g. a download/confirm button) that must stay reachable
   * without scrolling to the end of long content. */
  footer?: React.ReactNode;
}) {
  useEscapeKey(onClose);

  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;
    if (!open) return;

    const listener = CapacitorApp.addListener("backButton", () => {
      onClose();
    });

    return () => {
      void listener.then((h: PluginListenerHandle) => h.remove());
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className={styles.backdrop} onClick={onClose}>
      <div className={styles.sheet} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <h2 className={styles.title}>{title}</h2>
          <button
            type="button"
            className={styles.close}
            onClick={onClose}
            aria-label="Close"
          >
            <X size={20} strokeWidth={2} />
          </button>
        </div>
        <div className={styles.content}>{children}</div>
        {footer && <div className={styles.footer}>{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
