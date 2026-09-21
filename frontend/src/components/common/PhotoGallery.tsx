import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ImageLightbox, type LightboxImage } from "@/components/ui/ImageLightbox";
import styles from "./PhotoGallery.module.css";

export interface GalleryPhoto {
  id: string;
  url: string;
  /** Shown in the lightbox, and on the tile when `captionsOnTiles`. */
  caption?: string;
  subtitle?: string;
  /** Absent = not deletable by this viewer. */
  onDelete?: () => void;
}

/** How many tiles the mosaic draws at most; the rest hide behind a `+N`. */
const MAX_TILES = 4;

/** Mosaic of a set of photos, opening a swipeable lightbox on tap. Deliberately
 * has no per-tile delete control: the grid shows photographs, the lightbox
 * shows the controls. */
export function PhotoGallery({
  photos,
  captionsOnTiles = false,
}: {
  photos: GalleryPhoto[];
  /** An activity's gallery mixes several boats and several people, so it
   *  labels each tile; a single session's does not need to. */
  captionsOnTiles?: boolean;
}) {
  const { t } = useTranslation();
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  if (photos.length === 0) return null;

  const visible = photos.slice(0, MAX_TILES);
  const hidden = photos.length - visible.length;

  const images: LightboxImage[] = photos.map((p) => ({
    src: p.url,
    alt: p.caption ?? "",
    caption: p.caption,
    subtitle: p.subtitle,
    onDelete: p.onDelete,
  }));

  // A delete shrinks `photos` under a lightbox the parent left open.
  const index = openIndex === null ? null : Math.min(openIndex, photos.length - 1);

  return (
    <>
      <div className={styles.grid} data-count={visible.length}>
        {visible.map((photo, i) => {
          const isOverflowTile = hidden > 0 && i === visible.length - 1;
          return (
            <button
              key={photo.id}
              type="button"
              className={styles.tile}
              onClick={() => setOpenIndex(isOverflowTile ? visible.length : i)}
              aria-label={t("sessions.openGallery")}
            >
              <img src={photo.url} alt={photo.caption ?? ""} loading="lazy" />
              {captionsOnTiles && (photo.caption || photo.subtitle) && (
                <span className={styles.tileScrim}>
                  {photo.caption && <span className={styles.tileCaption}>{photo.caption}</span>}
                  {photo.subtitle && <span className={styles.tileSubtitle}>{photo.subtitle}</span>}
                </span>
              )}
              {isOverflowTile && <span className={styles.more}>+{hidden}</span>}
            </button>
          );
        })}
      </div>

      {index !== null && (
        <ImageLightbox images={images} index={index} onIndexChange={setOpenIndex} onClose={() => setOpenIndex(null)} />
      )}
    </>
  );
}
