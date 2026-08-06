import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ImagePlus } from "lucide-react";
import { putToUploadUrl } from "@/api/media";
import { postsService, postKeys } from "@/services/posts";
import { useToast } from "@/hooks/useToast";
import { Button } from "@/components/ui/Button";
import { PostBodyField } from "@/components/gruppi/PostBodyField";
import { richTextExcerpt } from "@/utils/richTextExcerpt";
import type { PostEventKind, PostOwnerType, UUID } from "@/types";
import styles from "./EntityFeed.module.css";
import photoGridStyles from "@/components/common/photoGrid.module.css";

interface PendingImage {
  imageId: UUID;
  previewUrl: string;
}

/** The write form: textarea + image picker/preview + publish. Rendered
 * inline on desktop (`.sf-desktop-only`, see `EntityFeed`'s form wrapper) and
 * inside a `Modal` on mobile — kept as its own component so it isn't defined
 * twice, since a permanently-visible compose box works poorly on a small
 * screen (it would push the whole feed below the fold).
 *
 * `eventRef` optionally ties the post to the activity/regatta it announces
 * (see `ClubEvents.tsx`/`GroupActivities.tsx` "announce this event" action) —
 * omitted for a plain news post. */
export function PostComposer({
  ownerType,
  ownerId,
  eventRef,
  onDone,
  flush,
}: {
  ownerType: PostOwnerType;
  ownerId: UUID;
  eventRef?: { kind: PostEventKind; id: UUID };
  onDone?: () => void;
  flush?: boolean;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [images, setImages] = useState<PendingImage[]>([]);
  const [uploading, setUploading] = useState(false);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: postKeys.list(ownerType, ownerId) });

  const addImages = async (files: FileList) => {
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const ticket = await postsService.uploadImage();
        await putToUploadUrl(ticket.upload_url, file, file.type || undefined);
        await postsService.confirmImage(ticket.image_id);
        setImages((prev) => [...prev, { imageId: ticket.image_id, previewUrl: URL.createObjectURL(file) }]);
      }
    } catch {
      notify(t("errors.generic"), "error");
    } finally {
      setUploading(false);
    }
  };

  const removeImage = (imageId: UUID) => {
    setImages((prev) => {
      const found = prev.find((i) => i.imageId === imageId);
      if (found) URL.revokeObjectURL(found.previewUrl);
      return prev.filter((i) => i.imageId !== imageId);
    });
  };

  const create = useMutation({
    mutationFn: () =>
      postsService.create({
        owner_type: ownerType,
        owner_id: ownerId,
        body,
        image_ids: images.map((i) => i.imageId),
        activity_id: eventRef?.kind === "activity" ? eventRef.id : undefined,
        regatta_id: eventRef?.kind === "regatta" ? eventRef.id : undefined,
      }),
    onSuccess: async () => {
      setBody("");
      images.forEach((i) => URL.revokeObjectURL(i.previewUrl));
      setImages([]);
      await invalidate();
      onDone?.();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  // `body` is rich-text HTML, so a whitespace-only draft is still `<p>   </p>`
  // — truthy as a string. Emptiness has to be decided on the rendered text.
  const hasBody = richTextExcerpt(body, 1) !== "";

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (hasBody) create.mutate();
  };

  return (
    <form onSubmit={submit} className={`${styles.feedForm} ${flush ? styles.feedFormFlush : ""}`}>
      <PostBodyField
        ownerType={ownerType}
        ownerId={ownerId}
        value={body}
        onChange={setBody}
        id="feed-body"
        placeholder={t("gruppi.newsBody")}
      />
      {images.length > 0 && (
        <div className={photoGridStyles.grid}>
          {images.map((img) => (
            <figure key={img.imageId}>
              <img src={img.previewUrl} alt="" />
              <Button
                type="button"
                variant="danger"
                className={`sf-btn--sm ${photoGridStyles.del}`}
                onClick={() => removeImage(img.imageId)}
              >
                ×
              </Button>
            </figure>
          ))}
        </div>
      )}
      <div className="sf-form__actions">
        <input
          type="file"
          accept="image/*"
          multiple
          id="feed-image"
          hidden
          onChange={(e) => {
            const files = e.target.files;
            if (files && files.length > 0) void addImages(files);
            e.target.value = "";
          }}
        />
        <Button
          type="button"
          variant="ghost"
          className="sf-btn--icon-sm"
          disabled={uploading}
          aria-label={t("common.upload")}
          onClick={() => document.getElementById("feed-image")?.click()}
        >
          <ImagePlus size={16} />
        </Button>
        <Button type="submit" disabled={create.isPending || uploading || !hasBody}>
          {t("gruppi.publish")}
        </Button>
      </div>
    </form>
  );
}
