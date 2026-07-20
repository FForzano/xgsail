import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Pencil, Plus, Trash2 } from "lucide-react";
import { putToUploadUrl } from "@/api/media";
import { postsService, postKeys } from "@/services/posts";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { PostBodyField } from "@/components/gruppi/PostBodyField";
import { userLabel, fmtDateTime } from "@/utils/format";
import { renderPostBody } from "@/utils/postFormat";
import type { Post, PostOwnerType, UUID } from "@/types";

interface PendingImage {
  imageId: UUID;
  previewUrl: string;
}

/** The write form: textarea + image picker/preview + publish. Rendered
 * inline on desktop (`.sf-desktop-only`, see `EntityFeed`'s form wrapper) and
 * inside a `Modal` on mobile — kept as its own component so it isn't defined
 * twice, since a permanently-visible compose box works poorly on a small
 * screen (it would push the whole feed below the fold). */
function PostComposer({
  ownerType,
  ownerId,
  onDone,
}: {
  ownerType: PostOwnerType;
  ownerId: UUID;
  onDone?: () => void;
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

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (body.trim()) create.mutate();
  };

  return (
    <form onSubmit={submit} className="sf-feed-form">
      <PostBodyField
        ownerType={ownerType}
        ownerId={ownerId}
        value={body}
        onChange={setBody}
        id="feed-body"
        placeholder={t("gruppi.newsBody")}
      />
      {images.length > 0 && (
        <div className="sf-photo-grid">
          {images.map((img) => (
            <figure key={img.imageId}>
              <img src={img.previewUrl} alt="" />
              <Button
                type="button"
                variant="danger"
                className="sf-btn--sm sf-photo__del"
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
        <Button type="submit" disabled={create.isPending || uploading || !body.trim()}>
          {t("gruppi.publish")}
        </Button>
      </div>
    </form>
  );
}

/** Inline body edit for an existing post — same `PostBodyField` as the
 * composer, but only touches `body` (images aren't editable after
 * publishing). Author-only, enforced again server-side. */
function PostEditForm({
  post,
  ownerType,
  ownerId,
  onDone,
}: {
  post: Post;
  ownerType: PostOwnerType;
  ownerId: UUID;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [body, setBody] = useState(post.body);

  const update = useMutation({
    mutationFn: () => postsService.update(post.id, { body }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: postKeys.list(ownerType, ownerId) });
      onDone();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  return (
    <form
      className="sf-feed-form"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        if (body.trim()) update.mutate();
      }}
    >
      <PostBodyField
        ownerType={ownerType}
        ownerId={ownerId}
        value={body}
        onChange={setBody}
        id={`feed-body-edit-${post.id}`}
        placeholder={t("gruppi.newsBody")}
        autoFocus
      />
      <div className="sf-form__actions">
        <Button type="button" variant="ghost" onClick={onDone}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={update.isPending || !body.trim()}>
          {t("common.save")}
        </Button>
      </div>
    </form>
  );
}

/** Feed shared by clubs and groups (see `backend/db/models/post.py` — a
 * single polymorphic `posts` table instead of one per owner type). Renders
 * the same for both: only `canManage` (create form + moderate any post)
 * differs by caller. */
export function EntityFeed({
  ownerType,
  ownerId,
  canManage,
}: {
  ownerType: PostOwnerType;
  ownerId: UUID;
  canManage: boolean;
}) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [composerOpen, setComposerOpen] = useState(false);
  const [editingId, setEditingId] = useState<UUID | null>(null);

  const posts = useQuery({
    queryKey: postKeys.list(ownerType, ownerId),
    queryFn: () => postsService.list(ownerType, ownerId),
  });

  const remove = useMutation({
    mutationFn: (id: UUID) => postsService.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: postKeys.list(ownerType, ownerId) }),
    onError: () => notify(t("errors.generic"), "error"),
  });

  return (
    <Card
      title={t("gruppi.news")}
      actions={
        canManage && (
          <Button
            variant="ghost"
            className="sf-btn--icon-sm sf-mobile-only"
            aria-label={t("gruppi.newPost")}
            onClick={() => setComposerOpen(true)}
          >
            <Plus size={16} />
          </Button>
        )
      }
    >
      {canManage && (
        <div className="sf-desktop-only">
          <PostComposer ownerType={ownerType} ownerId={ownerId} />
        </div>
      )}
      {canManage && composerOpen && (
        <Modal title={t("gruppi.newPost")} onClose={() => setComposerOpen(false)}>
          <PostComposer ownerType={ownerType} ownerId={ownerId} onDone={() => setComposerOpen(false)} />
        </Modal>
      )}

      {posts.isLoading ? (
        <Spinner />
      ) : posts.data && posts.data.length > 0 ? (
        <div className="sf-feed">
          {posts.data.map((p) => (
            <div key={p.id} className="sf-feed__post">
              <div className="sf-feed__post-head">
                <strong>{userLabel(p.author)}</strong>
                <span className="sf-muted">
                  {fmtDateTime(p.created_at)}
                  {p.updated_at && ` · ${t("gruppi.postEdited")}`}
                </span>
                {p.author_id === user?.id && (
                  <Button
                    variant="ghost"
                    className="sf-btn--icon-sm"
                    aria-label={t("common.edit")}
                    onClick={() => setEditingId(p.id)}
                  >
                    <Pencil size={14} />
                  </Button>
                )}
                {(canManage || p.author_id === user?.id) && (
                  <Button
                    variant="ghost"
                    className="sf-btn--icon-sm"
                    aria-label={t("common.delete")}
                    onClick={() => remove.mutate(p.id)}
                  >
                    <Trash2 size={14} />
                  </Button>
                )}
              </div>
              {editingId === p.id ? (
                <PostEditForm
                  post={p}
                  ownerType={ownerType}
                  ownerId={ownerId}
                  onDone={() => setEditingId(null)}
                />
              ) : (
                <p className="sf-feed__post-body">{renderPostBody(p.body)}</p>
              )}
              {p.images.length === 1 ? (
                <img className="sf-feed__post-image" src={p.images[0].url} alt="" />
              ) : p.images.length > 1 ? (
                <div className="sf-photo-grid sf-feed__post-image">
                  {p.images.map((img) => (
                    <figure key={img.image_id}>
                      <img src={img.url} alt="" />
                    </figure>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <EmptyState>{t("gruppi.emptyNews")}</EmptyState>
      )}
    </Card>
  );
}
