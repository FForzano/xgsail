import { useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useMediaUpload } from "@/hooks/useMediaUpload";
import { Button } from "@/components/ui/Button";
import { ImageCropModal } from "@/components/common/ImageCropModal";
import type { UUID } from "@/types";

/** File picker + presign/PUT/confirm state, for any parent-mediated image.
 * Pass `crop` to have the user reposition/zoom a square crop before it's
 * uploaded (e.g. profile pictures). Pass `icon` to render an icon-only
 * button (with `label` as its `aria-label`) instead of the default text
 * button. */
export function ImageUploader({
  create,
  confirm,
  onDone,
  label,
  accept = "image/*",
  crop = false,
  icon,
}: {
  create: () => Promise<{ image_id: UUID; upload_url: string }>;
  confirm: (id: UUID) => Promise<unknown>;
  onDone?: () => void | Promise<void>;
  label?: string;
  accept?: string;
  crop?: boolean;
  icon?: ReactNode;
}) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [cropSrc, setCropSrc] = useState<string | null>(null);
  const { upload, busy, error } = useMediaUpload({ create, confirm, onDone });

  const closeCrop = () => {
    if (cropSrc) URL.revokeObjectURL(cropSrc);
    setCropSrc(null);
  };

  return (
    <span className="sf-uploader">
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) {
            if (crop) {
              setCropSrc(URL.createObjectURL(f));
            } else {
              void upload(f);
            }
          }
          e.target.value = "";
        }}
      />
      {icon ? (
        <Button
          type="button"
          variant="ghost"
          className="sf-btn--icon-sm"
          disabled={busy}
          aria-label={label ?? t("common.upload")}
          onClick={() => inputRef.current?.click()}
        >
          {icon}
        </Button>
      ) : (
        <Button
          type="button"
          variant="ghost"
          className="sf-btn--sm"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          {busy ? "…" : (label ?? t("common.upload"))}
        </Button>
      )}
      {error && <span className="sf-form__error"> {error}</span>}
      {cropSrc && (
        <ImageCropModal
          imageSrc={cropSrc}
          title={label}
          onCancel={closeCrop}
          onCropped={(blob) => {
            closeCrop();
            void upload(new File([blob], "avatar.jpg", { type: "image/jpeg" }));
          }}
        />
      )}
    </span>
  );
}
