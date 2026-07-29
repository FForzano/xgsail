import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import { ImageCropModal } from "@/components/common/ImageCropModal";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { ColorPicker } from "@/components/ui/ColorPicker";
import { Spinner } from "@/components/ui/Spinner";
import { usePersistentState } from "@/hooks/usePersistentState";
import { useToast } from "@/hooks/useToast";
import { renderShareCardToBlob, shareOrDownloadImage } from "@/utils/shareImage";
import { ShareCard, type ShareCardData } from "./ShareCard";
import { ShareCameraModal, cameraCaptureSupported } from "./ShareCameraModal";
import styles from "./ShareImageModal.module.css";

const CARD_WIDTH = 1080;
const CARD_HEIGHT = 1920;
const PREVIEW_WIDTH = 260;
const PREVIEW_SCALE = PREVIEW_WIDTH / CARD_WIDTH;

// Design-system colors plus plain white/black, which are what actually work
// on an arbitrary photo. The free `<input type="color">` covers the rest.
const TEXT_PRESETS = ["#ffffff", "#0b1f33", "#2f9be0", "#e0b24a"];
const TRACK_PRESETS = ["#ff9500", "#ffffff", "#2f9be0", "#3fbf7f", "#e05a5a"];

/** Lets the user pick what shows up in a shareable image of their session
 * (see ShareCard) and then share it via the native share sheet or download
 * it — see docs discussion: deliberately image-only, no public link. */
export function ShareImageModal({ data, onClose }: { data: ShareCardData; onClose: () => void }) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const cardRef = useRef<HTMLDivElement>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);
  const galleryInputRef = useRef<HTMLInputElement>(null);
  const [includeBoatPhoto, setIncludeBoatPhoto] = useState(true);
  const [includeTrack, setIncludeTrack] = useState(true);
  const [includeStats, setIncludeStats] = useState(true);
  const [includeTitle, setIncludeTitle] = useState(true);
  const [includeCrew, setIncludeCrew] = useState(true);
  const [busy, setBusy] = useState(false);
  // Remembered per device: whoever settled on a look for their shares keeps
  // it for the next session without re-picking.
  const [textColor, setTextColor] = usePersistentState("xgsail.share.textColor", "#ffffff");
  const [trackColor, setTrackColor] = usePersistentState("xgsail.share.trackColor", "#ff9500");
  // Swaps in a photo taken/picked just for this share (never uploaded to the
  // session). Local object URL, revoked on replace/unmount so it doesn't leak.
  const [customPhotoUrl, setCustomPhotoUrl] = useState<string | null>(null);
  useEffect(() => () => {
    if (customPhotoUrl) URL.revokeObjectURL(customPhotoUrl);
  }, [customPhotoUrl]);
  const [cameraOpen, setCameraOpen] = useState(false);
  // Set once the in-app camera turns out to be unusable (permission refused):
  // from then on "Scatta" goes straight to the system camera. Retrying the
  // in-app one would just fail again, and the fallback can't be opened from
  // here — a file input only opens from a real user gesture, which the async
  // getUserMedia rejection no longer is.
  const [cameraBlocked, setCameraBlocked] = useState(false);
  // A picked (or system-camera) photo is almost never 9:16, so it goes through
  // the cropper before landing on the card — otherwise the card's
  // `object-fit: cover` would silently cut its sides. The in-app camera skips
  // this: it already shoots in frame.
  const [pendingCropUrl, setPendingCropUrl] = useState<string | null>(null);
  const cardData = { ...data, boatPhotoUrl: customPhotoUrl ?? data.boatPhotoUrl };

  function commitPhoto(blob: Blob) {
    if (customPhotoUrl) URL.revokeObjectURL(customPhotoUrl);
    setCustomPhotoUrl(URL.createObjectURL(blob));
    setIncludeBoatPhoto(true);
  }

  function closeCrop() {
    if (pendingCropUrl) URL.revokeObjectURL(pendingCropUrl);
    setPendingCropUrl(null);
  }

  const pickFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) setPendingCropUrl(URL.createObjectURL(file));
  };

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
            textColor={textColor}
            trackColor={trackColor}
          />
        </div>
      </div>
      {/* Two inputs, deliberately: `capture` is what makes mobile open the
          system camera instead of the gallery, so the fallback shooter and the
          "choose an existing photo" picker can't be the same element. */}
      <input
        ref={photoInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        onChange={pickFile}
      />
      <input ref={galleryInputRef} type="file" accept="image/*" hidden onChange={pickFile} />
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
          onClick={() =>
            cameraCaptureSupported && !cameraBlocked
              ? setCameraOpen(true)
              : photoInputRef.current?.click()
          }
        >
          {t("sessions.shareImage.takePhoto")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          className={styles.takePhotoBtn}
          onClick={() => galleryInputRef.current?.click()}
        >
          {t("sessions.shareImage.choosePhoto")}
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
      <div className={styles.colors}>
        <ColorPicker
          label={t("sessions.shareImage.textColor")}
          value={textColor}
          presets={TEXT_PRESETS}
          onChange={setTextColor}
        />
        <ColorPicker
          label={t("sessions.shareImage.trackColor")}
          value={trackColor}
          presets={TRACK_PRESETS}
          onChange={setTrackColor}
        />
      </div>
      <Button onClick={handleShare} disabled={busy}>
        {busy ? <Spinner inline /> : t("sessions.shareImage.cta")}
      </Button>
      {cameraOpen && (
        <ShareCameraModal
          onCancel={() => setCameraOpen(false)}
          onCaptured={(blob) => {
            commitPhoto(blob);
            setCameraOpen(false);
          }}
          onUnavailable={() => {
            setCameraOpen(false);
            setCameraBlocked(true);
            notify(t("sessions.shareImage.cameraUnavailable"), "error");
          }}
        />
      )}
      {pendingCropUrl && (
        <ImageCropModal
          imageSrc={pendingCropUrl}
          aspect={CARD_WIDTH / CARD_HEIGHT}
          cropShape="rect"
          outputWidth={CARD_WIDTH}
          outputHeight={CARD_HEIGHT}
          previewHeight={420}
          onCancel={closeCrop}
          onCropped={(blob) => {
            commitPhoto(blob);
            closeCrop();
          }}
        />
      )}
    </Modal>
  );
}
