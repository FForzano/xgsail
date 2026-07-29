import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Camera } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import styles from "./ShareCameraModal.module.css";

/** Whether an in-app camera is possible at all — the system camera is the
 * fallback everywhere else (older WebViews, desktop browsers with no camera). */
export const cameraCaptureSupported =
  typeof navigator !== "undefined" && typeof navigator.mediaDevices?.getUserMedia === "function";

/** Shoots the share photo inside the app, framed in the card's real 9:16
 * aspect — the system camera can't show our frame, so a photo taken there
 * always needs cropping afterwards and the user never sees what they'll get
 * while shooting. Here the preview IS the output frame.
 *
 * Hands back a ready-to-use 1080x1920 JPEG, so no crop step follows. */
export function ShareCameraModal({
  onCancel,
  onCaptured,
  onUnavailable,
}: {
  onCancel: () => void;
  onCaptured: (blob: Blob) => void;
  /** Permission denied or no usable camera — the caller falls back. */
  onUnavailable: () => void;
}) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let stream: MediaStream | null = null;

    void (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          // `ideal`, never `exact`: a front camera or a laptop webcam can't
          // deliver 1080x1920, and the capture below normalizes whatever
          // resolution we actually get anyway.
          video: {
            facingMode: { ideal: "environment" },
            width: { ideal: 1080 },
            height: { ideal: 1920 },
          },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        if (videoRef.current) videoRef.current.srcObject = stream;
        setReady(true);
      } catch {
        if (!cancelled) onUnavailable();
      }
    })();

    // Stopping the tracks is what turns the camera (and its indicator) off —
    // dropping the element alone leaves the stream live.
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [onUnavailable]);

  const shoot = async () => {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    setBusy(true);
    try {
      onCaptured(await captureFrame(video));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={t("sessions.shareImage.cameraTitle")} onClose={onCancel}>
      <div className={styles.stage}>
        <video ref={videoRef} className={styles.video} autoPlay playsInline muted />
        {!ready && (
          <div className={styles.loading}>
            <Spinner />
          </div>
        )}
      </div>
      <p className="sf-muted">{t("sessions.shareImage.cameraHint")}</p>
      <div className="sf-form__actions">
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button
          type="button"
          className="sf-btn--icon"
          disabled={!ready || busy}
          aria-label={t("sessions.shareImage.shutter")}
          onClick={() => void shoot()}
        >
          <Camera size={22} strokeWidth={1.75} />
        </Button>
      </div>
    </Modal>
  );
}

const OUT_WIDTH = 1080;
const OUT_HEIGHT = 1920;

/** Draws the frame on screen right now into a 1080x1920 canvas, centre-cropped
 * exactly the way the preview's `object-fit: cover` crops it — so what the
 * viewfinder showed is what the card gets. */
function captureFrame(video: HTMLVideoElement): Promise<Blob> {
  const { videoWidth: vw, videoHeight: vh } = video;
  const target = OUT_WIDTH / OUT_HEIGHT;
  let sw = vw;
  let sh = vh;
  if (vw / vh > target) sw = vh * target;
  else sh = vw / target;

  const canvas = document.createElement("canvas");
  canvas.width = OUT_WIDTH;
  canvas.height = OUT_HEIGHT;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas not supported");
  ctx.drawImage(video, (vw - sw) / 2, (vh - sh) / 2, sw, sh, 0, 0, OUT_WIDTH, OUT_HEIGHT);

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("Capture failed"))),
      "image/jpeg",
      0.92,
    );
  });
}
