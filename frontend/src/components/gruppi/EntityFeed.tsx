import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Sailboat, Trash2, Trophy } from "lucide-react";
import { postsService, postKeys } from "@/services/posts";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { PostBodyField } from "@/components/gruppi/PostBodyField";
import { PostComposer } from "@/components/gruppi/PostComposer";
import { RichText } from "@/components/ui/RichText";
import { userLabel, fmtDateTime } from "@/utils/format";
import { richTextExcerpt } from "@/utils/richTextExcerpt";
import type { Post, PostOwnerType, UUID } from "@/types";
import styles from "./EntityFeed.module.css";
import photoGridStyles from "@/components/common/photoGrid.module.css";

/** Nested preview of the activity/regatta a post announces — a Facebook
 * "shared post" style card (thumbnail + title + description) embedded below
 * the announcement's own text, linking through to the event. Set by
 * `ClubEvents.tsx`/`GroupActivities.tsx`'s "announce this event" action. */
function PostEventCard({
  event,
  dataTour,
}: {
  event: NonNullable<Post["event"]>;
  /** `data-tour` anchor — set only on the first such card by callers that use
   * this in a guided-tour step, following `EventRow`'s `dataTour` convention. */
  dataTour?: string;
}) {
  const { t } = useTranslation();
  const href = event.kind === "activity" ? `/diario/activities/${event.id}` : `/diario/regate/regatta/${event.id}`;
  const title = event.title ?? (event.type ? t(`activities.types.${event.type}`) : t(`gruppi.eventKind.${event.kind}`));
  return (
    <Link to={href} className={styles.eventCard} data-tour={dataTour}>
      <div className={styles.eventCardMedia}>
        {event.image ? (
          <img src={event.image.url} alt="" />
        ) : (
          <div className={styles.eventCardPlaceholder} data-kind={event.kind} aria-hidden>
            {event.kind === "regatta" ? <Trophy size={24} /> : <Sailboat size={24} />}
          </div>
        )}
      </div>
      <div className={styles.eventCardBody}>
        <span className={`sf-badge ${event.kind === "regatta" ? "sf-badge--regatta" : "sf-badge--activity"}`}>
          {t(`gruppi.eventKind.${event.kind}`)}
        </span>
        <strong className={styles.eventCardTitle}>{title}</strong>
        {event.description && <p className={styles.eventCardDescription}>{event.description}</p>}
      </div>
    </Link>
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
  // `"<p></p>"` is a truthy string, so emptiness is a question about the text
  // the body renders — a mention-only post has no plain text of its own but
  // does carry its `@label`, and counts as written.
  const hasBody = richTextExcerpt(body, 1) !== "";

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
      className={styles.feedForm}
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        if (hasBody) update.mutate();
      }}
    >
      <PostBodyField
        ownerType={ownerType}
        ownerId={ownerId}
        value={body}
        onChange={setBody}
        id={`feed-body-edit-${post.id}`}
        placeholder={t("gruppi.newsBody")}
      />
      <div className="sf-form__actions">
        <Button type="button" variant="ghost" onClick={onDone}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={update.isPending || !hasBody}>
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
  dataTour,
  eventCardDataTour,
}: {
  ownerType: PostOwnerType;
  ownerId: UUID;
  canManage: boolean;
  /** `data-tour` anchor on the feed's list/empty-state container — opt-in per
   * caller (e.g. the club news route), never hardcoded here since this
   * component is shared by clubs and groups. */
  dataTour?: string;
  /** `data-tour` anchor forwarded to the first post's `PostEventCard`, if
   * any — same single-item convention as `EventRow`'s `dataTour`. */
  eventCardDataTour?: string;
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

  const firstEventPostId = posts.data?.find((p) => p.event)?.id;

  return (
    <>
      {canManage && (
        <div className={`${styles.newMobile} sf-mobile-only`}>
          <Button
            variant="ghost"
            className="sf-btn--icon-sm"
            aria-label={t("gruppi.newPost")}
            onClick={() => setComposerOpen(true)}
          >
            <Plus size={16} />
          </Button>
        </div>
      )}
      {canManage && (
        <div className="sf-desktop-only">
          <PostComposer ownerType={ownerType} ownerId={ownerId} />
        </div>
      )}
      {canManage && composerOpen && (
        <Modal title={t("gruppi.newPost")} onClose={() => setComposerOpen(false)}>
          <PostComposer ownerType={ownerType} ownerId={ownerId} onDone={() => setComposerOpen(false)} flush />
        </Modal>
      )}

      <div data-tour={dataTour}>
      {posts.isLoading ? (
        <Spinner />
      ) : posts.data && posts.data.length > 0 ? (
        <div className={styles.feed}>
          {posts.data.map((p) => (
            <div key={p.id} className={styles.post}>
              <div className={styles.postHead}>
                <div className={styles.postMeta}>
                  <strong>{userLabel(p.author)}</strong>
                  <span className="sf-muted">
                    {fmtDateTime(p.created_at)}
                    {p.updated_at && ` · ${t("gruppi.postEdited")}`}
                  </span>
                </div>
                <span className={styles.postActions}>
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
                </span>
              </div>
              {editingId === p.id ? (
                <PostEditForm
                  post={p}
                  ownerType={ownerType}
                  ownerId={ownerId}
                  onDone={() => setEditingId(null)}
                />
              ) : (
                <RichText html={p.body} tier="basic" mentions className={styles.postBody} />
              )}
              {p.event && (
                <PostEventCard
                  event={p.event}
                  dataTour={p.id === firstEventPostId ? eventCardDataTour : undefined}
                />
              )}
              {p.images.length === 1 ? (
                <img className={styles.postImage} src={p.images[0].url} alt="" />
              ) : p.images.length > 1 ? (
                <div className={`${photoGridStyles.grid} ${styles.postImage}`}>
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
      </div>
    </>
  );
}
