import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { useMediaUpload } from "@/hooks/useMediaUpload";
import { Button } from "@/components/ui/Button";
import type { UUID } from "@/types";

/** File picker + presign/PUT/confirm state, for any parent-mediated image. */
export function ImageUploader({
  create,
  confirm,
  onDone,
  label,
  accept = "image/*",
}: {
  create: () => Promise<{ image_id: UUID; upload_url: string }>;
  confirm: (id: UUID) => Promise<unknown>;
  onDone?: () => void | Promise<void>;
  label?: string;
  accept?: string;
}) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const { upload, busy, error } = useMediaUpload({ create, confirm, onDone });

  return (
    <span className="sf-uploader">
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void upload(f);
          e.target.value = "";
        }}
      />
      <Button
        type="button"
        variant="ghost"
        className="sf-btn--sm"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
      >
        {busy ? "…" : (label ?? t("common.upload"))}
      </Button>
      {error && <span className="sf-form__error"> {error}</span>}
    </span>
  );
}
