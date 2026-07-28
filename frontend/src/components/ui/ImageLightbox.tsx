import { useTranslation } from "react-i18next";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import styles from "./ImageLightbox.module.css";

/** Full-screen click-to-enlarge viewer for a single image — Esc or a
 * backdrop click closes it. Not built on Modal: a lightbox wants the image
 * itself centered on a dark backdrop, not Modal's card chrome (title bar,
 * bordered panel, body padding), which would just get in the way here.
 *
 * Shares Modal's `sf-modal__backdrop` marker class so a touch starting on
 * the lightbox is excluded from AppShell's swipe/pull gesture recognizer
 * (see useAppShellGestures.ts's BAIL_SELECTOR) the same way a Modal already is. */
export function ImageLightbox({ src, alt, onClose }: { src: string; alt: string; onClose: () => void }) {
  const { t } = useTranslation();
  useEscapeKey(onClose);

  return (
    <div className={`sf-modal__backdrop ${styles.backdrop}`} onClick={onClose} role="dialog" aria-modal="true">
      <img src={src} alt={alt} className={styles.image} onClick={(e) => e.stopPropagation()} />
      <button className={styles.close} onClick={onClose} aria-label={t("common.close")}>
        ×
      </button>
    </div>
  );
}
