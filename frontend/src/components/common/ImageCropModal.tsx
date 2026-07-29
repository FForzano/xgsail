import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import Cropper, { type Area } from "react-easy-crop";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { getCroppedImageBlob } from "@/utils/cropImage";

/** Lets the user pan/zoom a crop of `imageSrc` before it's used.
 * `imageSrc` must be an object URL owned by the caller (revoked on close) —
 * except when it's an already-hosted photo the caller is re-cropping in
 * place (see ShareImageModal's "Ritaglia foto" on the default boat photo),
 * where it's the remote URL itself and there's nothing to revoke.
 *
 * That remote case is also the only one where "Apply" can fail: cropImage.ts
 * loads with crossOrigin="anonymous" so the canvas can read pixels back out,
 * which needs the host to send CORS headers (true for this app's own MinIO/S3
 * bucket in every deployment this modal ships against, but not guaranteed for
 * an arbitrary photo host) — shown inline rather than left as a silently
 * stuck "…" button.
 *
 * Square and round by default — that's the avatar/logo case every uploader
 * goes through (see ImageUploader). The share card passes its own 9:16 frame
 * and output size instead, so the exported image isn't silently centre-cropped
 * (see ShareImageModal). */
export function ImageCropModal({
  imageSrc,
  onCancel,
  onCropped,
  title,
  aspect = 1,
  cropShape = "round",
  outputWidth = 512,
  outputHeight = outputWidth,
  previewHeight = 320,
}: {
  imageSrc: string;
  onCancel: () => void;
  onCropped: (blob: Blob) => void;
  /** Defaults to the profile-picture wording, which is wrong for every other
   * caller (boat/club photos, the share card) — pass this explicitly there. */
  title?: string;
  aspect?: number;
  cropShape?: "round" | "rect";
  outputWidth?: number;
  outputHeight?: number;
  /** Height of the cropping stage; a tall frame needs more room than a square. */
  previewHeight?: number;
}) {
  const { t } = useTranslation();
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [croppedArea, setCroppedArea] = useState<Area | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onCropComplete = useCallback((_area: Area, areaPixels: Area) => {
    setCroppedArea(areaPixels);
  }, []);

  const confirm = async () => {
    if (!croppedArea) return;
    setBusy(true);
    setError(null);
    try {
      const blob = await getCroppedImageBlob(imageSrc, croppedArea, outputWidth, outputHeight);
      onCropped(blob);
    } catch {
      setError(t("common.cropFailed"));
      setBusy(false);
    }
  };

  return (
    <Modal title={title ?? t("profile.cropImage")} onClose={onCancel}>
      <div style={{ position: "relative", width: "100%", height: previewHeight, background: "#000" }}>
        <Cropper
          image={imageSrc}
          crop={crop}
          zoom={zoom}
          aspect={aspect}
          cropShape={cropShape}
          showGrid={false}
          onCropChange={setCrop}
          onZoomChange={setZoom}
          onCropComplete={onCropComplete}
        />
      </div>
      <div className="sf-form__row" style={{ marginTop: "1rem" }}>
        <label htmlFor="crop-zoom">{t("profile.zoom")}</label>
        <input
          id="crop-zoom"
          type="range"
          min={1}
          max={3}
          step={0.01}
          value={zoom}
          onChange={(e) => setZoom(Number(e.target.value))}
        />
      </div>
      {error && <p className="sf-form__error">{error}</p>}
      <div className="sf-form__actions">
        <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
          {t("common.cancel")}
        </Button>
        <Button type="button" onClick={() => void confirm()} disabled={busy || !croppedArea}>
          {busy ? "…" : t("common.apply")}
        </Button>
      </div>
    </Modal>
  );
}
