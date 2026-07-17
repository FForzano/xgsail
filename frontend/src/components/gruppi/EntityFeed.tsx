import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { postsService, postKeys } from "@/services/posts";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { useMediaUpload } from "@/hooks/useMediaUpload";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { TextAreaField } from "@/components/ui/InputField";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { userLabel, fmtDateTime } from "@/utils/format";
import type { PostOwnerType, UUID } from "@/types";

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
  const [body, setBody] = useState("");
  const [imageId, setImageId] = useState<UUID | null>(null);

  const posts = useQuery({
    queryKey: postKeys.list(ownerType, ownerId),
    queryFn: () => postsService.list(ownerType, ownerId),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: postKeys.list(ownerType, ownerId) });

  const { upload, busy: uploading } = useMediaUpload({
    create: postsService.uploadImage,
    confirm: (id) => postsService.confirmImage(id).then(() => setImageId(id)),
  });

  const create = useMutation({
    mutationFn: () => postsService.create({ owner_type: ownerType, owner_id: ownerId, body, image_id: imageId }),
    onSuccess: async () => {
      setBody("");
      setImageId(null);
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  const remove = useMutation({
    mutationFn: (id: UUID) => postsService.remove(id),
    onSuccess: invalidate,
    onError: () => notify(t("errors.generic"), "error"),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (body.trim()) create.mutate();
  };

  return (
    <Card title={t("gruppi.news")}>
      {canManage && (
        <form onSubmit={submit} className="sf-feed-form">
          <TextAreaField
            label={t("gruppi.newsBody")}
            id="feed-body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            required
          />
          <div className="sf-form__actions">
            <input
              type="file"
              accept="image/*"
              id="feed-image"
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
              disabled={uploading}
              onClick={() => document.getElementById("feed-image")?.click()}
            >
              {imageId ? t("common.preview") : t("common.upload")}
            </Button>
            <Button type="submit" disabled={create.isPending || !body.trim()}>
              {t("gruppi.publish")}
            </Button>
          </div>
        </form>
      )}

      {posts.isLoading ? (
        <Spinner />
      ) : posts.data && posts.data.length > 0 ? (
        <div className="sf-feed">
          {posts.data.map((p) => (
            <div key={p.id} className="sf-feed__post">
              <div className="sf-feed__post-head">
                <strong>{userLabel(p.author)}</strong>
                <span className="sf-muted">{fmtDateTime(p.created_at)}</span>
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
              <p>{p.body}</p>
              {p.image && <img className="sf-feed__post-image" src={p.image.url} alt="" />}
            </div>
          ))}
        </div>
      ) : (
        <EmptyState>{t("gruppi.emptyNews")}</EmptyState>
      )}
    </Card>
  );
}
