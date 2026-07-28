import type { ReactNode } from "react";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import styles from "./Modal.module.css";

// Minimal accessible modal: Esc closes, backdrop click closes, body content
// is arbitrary. Feature forms live inside as children.
export function Modal({
  title,
  onClose,
  children,
}: {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
}) {
  useEscapeKey(onClose);

  return (
    <div className={`sf-modal__backdrop ${styles.backdrop}`} onClick={onClose}>
      <div
        className={styles.modal}
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
      </div>
    </div>
  );
}
