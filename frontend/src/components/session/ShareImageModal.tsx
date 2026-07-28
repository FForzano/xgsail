import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useToast } from "@/hooks/useToast";
import { renderShareCardToBlob, shareOrDownloadImage } from "@/utils/shareImage";
import { ShareCard, type ShareCardData } from "./ShareCard";
import styles from "./ShareImageModal.module.css";

const CARD_WIDTH = 1080;
const CARD_HEIGHT = 1920;
const PREVIEW_WIDTH = 260;
const PREVIEW_SCALE = PREVIEW_WIDTH / CARD_WIDTH;

/** Lets the user pick what shows up in a shareable image of their session
 * (see ShareCard) and then share it via the native share sheet or download
 * it — see docs discussion: deliberately image-only, no public link. */
export function ShareImageModal({ data, onClose }: { data: ShareCardData; onClose: () => void }) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const cardRef = useRef<HTMLDivElement>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);
  const [includeBoatPhoto, setIncludeBoatPhoto] = useState(true);
  const [includeTrack, setIncludeTrack] = useState(true);
  const [includeStats, setIncludeStats] = useState(true);
  const [includeTitle, setIncludeTitle] = useState(true);
  const [includeCrew, setIncludeCrew] = useState(true);
  const [busy, setBusy] = useState(false);
  // Swaps in a photo taken/picked just for this share (never uploaded to the
  // session) — `capture="environment"` opens the camera directly on mobile,
  // falls back to a plain file picker elsewhere. Local object URL, revoked
  // on replace/unmount so it doesn't leak.
  const [customPhotoUrl, setCustomPhotoUrl] = useState<string | null>(null);
  useEffect(() => () => {
    if (customPhotoUrl) URL.revokeObjectURL(customPhotoUrl);
  }, [customPhotoUrl]);
  const cardData = { ...data, boatPhotoUrl: customPhotoUrl ?? data.boatPhotoUrl };

  async function handleShare() {
    if (!cardRef.current) return;
    setBusy(true);
    try {
      const blob = await renderShareCardToBlob(cardRef.current);
      const result = await shareOrDownloadImage(blob, `${data.boatName || "session"}.png`, data.boatName);
      if (result === "downloaded") notify(t("sessions.shareImage.downloaded"), "success");
    } catch {
      notify(t("errors.generic"), "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={t("sessions.shareImage.title")} onClose={onClose}>
      <div className={styles.previewWrap} style={{ width: PREVIEW_WIDTH, height: CARD_HEIGHT * PREVIEW_SCALE }}>
        <div className={styles.previewScale} style={{ transform: `scale(${PREVIEW_SCALE})` }}>
          <ShareCard
            ref={cardRef}
            data={cardData}
            includeBoatPhoto={includeBoatPhoto}
            includeTrack={includeTrack}
            includeStats={includeStats}
            includeTitle={includeTitle}
            includeCrew={includeCrew}
          />
        </div>
      </div>
      <input
        ref={photoInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (!f) return;
          if (customPhotoUrl) URL.revokeObjectURL(customPhotoUrl);
          setCustomPhotoUrl(URL.createObjectURL(f));
          setIncludeBoatPhoto(true);
        }}
      />
      <div className={styles.options}>
        <label className={styles.option}>
          <input
            type="checkbox"
            checked={includeBoatPhoto}
            onChange={(e) => setIncludeBoatPhoto(e.target.checked)}
          />
          {t("sessions.shareImage.includeBoatPhoto")}
        </label>
        <Button
          type="button"
          variant="ghost"
          className={styles.takePhotoBtn}
          onClick={() => photoInputRef.current?.click()}
        >
          {customPhotoUrl ? t("sessions.shareImage.retakePhoto") : t("sessions.shareImage.takePhoto")}
        </Button>
        <label className={styles.option}>
          <input type="checkbox" checked={includeTrack} onChange={(e) => setIncludeTrack(e.target.checked)} />
          {t("sessions.shareImage.includeTrack")}
        </label>
        <label className={styles.option}>
          <input type="checkbox" checked={includeStats} onChange={(e) => setIncludeStats(e.target.checked)} />
          {t("sessions.shareImage.includeStats")}
        </label>
        <label className={styles.option}>
          <input type="checkbox" checked={includeTitle} onChange={(e) => setIncludeTitle(e.target.checked)} />
          {t("sessions.shareImage.includeTitle")}
        </label>
        <label className={styles.option}>
          <input type="checkbox" checked={includeCrew} onChange={(e) => setIncludeCrew(e.target.checked)} />
          {t("sessions.shareImage.includeCrew")}
        </label>
      </div>
      <Button onClick={handleShare} disabled={busy}>
        {busy ? <Spinner inline /> : t("sessions.shareImage.cta")}
      </Button>
    </Modal>
  );
}
