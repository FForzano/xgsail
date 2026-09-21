import { ChevronLeft, ChevronRight, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useRef, type TouchEvent as ReactTouchEvent } from "react";
import { useTranslation } from "react-i18next";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import styles from "./ImageLightbox.module.css";

export interface LightboxImage {
  src: string;
  alt?: string;
  /** Primary line in the lightbox chrome, e.g. who took it. */
  caption?: string;
  /** Secondary, dimmer line, e.g. the boat or a date. */
  subtitle?: string;
  /** Absent = this viewer may not delete this photo; no button is rendered. */
  onDelete?: () => void;
}

interface SingleProps {
  src: string;
  alt: string;
  onClose: () => void;
}

interface GalleryProps {
  images: LightboxImage[];
  index: number;
  onIndexChange: (i: number) => void;
  onClose: () => void;
}

/** Horizontal travel (px) past which a touch counts as a swipe rather than a tap. */
const SWIPE_THRESHOLD = 48;

/** Full-screen click-to-enlarge viewer — Esc or a backdrop click closes it.
 * Not built on Modal: a lightbox wants the image itself centered on a dark
 * backdrop, not Modal's card chrome (title bar, bordered panel, body padding),
 * which would just get in the way here.
 *
 * Two forms: a single `{src, alt}` image, or a controlled gallery
 * (`{images, index, onIndexChange}`) where the parent owns the current index.
 *
 * Shares Modal's `sf-modal__backdrop` marker class so a touch starting on
 * the lightbox is excluded from AppShell's swipe/pull gesture recognizer
 * (see useAppShellGestures.ts's BAIL_SELECTOR) the same way a Modal already is. */
export function ImageLightbox(props: SingleProps | GalleryProps) {
  const { t } = useTranslation();
  const { onClose } = props;
  const gallery = "images" in props;
  const images: LightboxImage[] = gallery ? props.images : [{ src: props.src, alt: props.alt }];
  const index = gallery ? Math.min(Math.max(props.index, 0), Math.max(images.length - 1, 0)) : 0;
  const onIndexChange = gallery ? props.onIndexChange : undefined;

  useEscapeKey(onClose);

  const count = images.length;
  const go = useCallback(
    (delta: number) => {
      if (!onIndexChange) return;
      // Deliberately no wrap-around: stopping at the ends is how a
      // swipe-happy user can tell they reached the first/last photo.
      const next = index + delta;
      if (next >= 0 && next < count) onIndexChange(next);
    },
    [onIndexChange, index, count],
  );

  useEffect(() => {
    if (!onIndexChange) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") go(-1);
      else if (e.key === "ArrowRight") go(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onIndexChange, go]);

  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const onTouchStart = (e: ReactTouchEvent) => {
    const touch = e.touches[0];
    touchStart.current = { x: touch.clientX, y: touch.clientY };
  };
  const onTouchEnd = (e: ReactTouchEvent) => {
    const start = touchStart.current;
    touchStart.current = null;
    if (!start) return;
    const touch = e.changedTouches[0];
    const dx = touch.clientX - start.x;
    const dy = touch.clientY - start.y;
    if (Math.abs(dx) < SWIPE_THRESHOLD || Math.abs(dx) <= Math.abs(dy)) return;
    go(dx < 0 ? 1 : -1);
  };

  const current = images[index];
  if (!current) return null;

  const hasChrome = Boolean(current.caption || current.subtitle);

  return (
    <div className={`sf-modal__backdrop ${styles.backdrop}`} onClick={onClose} role="dialog" aria-modal="true">
      <div className={styles.stage} onClick={(e) => e.stopPropagation()}>
        <img
          src={current.src}
          alt={current.alt ?? current.caption ?? ""}
          className={styles.image}
          onTouchStart={onTouchStart}
          onTouchEnd={onTouchEnd}
        />
        {hasChrome && (
          <div className={styles.scrim}>
            {current.caption && <p className={styles.caption}>{current.caption}</p>}
            {current.subtitle && <p className={styles.subtitle}>{current.subtitle}</p>}
          </div>
        )}
      </div>

      {count > 1 && (
        <>
          <button
            className={`${styles.nav} ${styles.navPrev}`}
            onClick={(e) => {
              e.stopPropagation();
              go(-1);
            }}
            disabled={index === 0}
            aria-label={t("common.previousImage")}
          >
            <ChevronLeft size={28} />
          </button>
          <button
            className={`${styles.nav} ${styles.navNext}`}
            onClick={(e) => {
              e.stopPropagation();
              go(1);
            }}
            disabled={index === count - 1}
            aria-label={t("common.nextImage")}
          >
            <ChevronRight size={28} />
          </button>
          <p className={styles.counter}>
            {index + 1} / {count}
          </p>
        </>
      )}

      {current.onDelete && (
        <button
          className={styles.delete}
          onClick={(e) => {
            e.stopPropagation();
            // Deleting the last remaining image is the parent's call: it owns
            // both the list and `index`, so it decides whether to close.
            current.onDelete?.();
          }}
          aria-label={t("sessions.deletePhoto")}
        >
          <Trash2 size={20} />
        </button>
      )}

      <button className={styles.close} onClick={onClose} aria-label={t("common.close")}>
        <X size={22} />
      </button>
    </div>
  );
}
