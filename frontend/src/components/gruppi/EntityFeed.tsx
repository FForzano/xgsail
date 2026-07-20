import { useMemo, useRef, useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bold, ImagePlus, Italic, Link2, Plus, Trash2, Underline } from "lucide-react";
import { putToUploadUrl } from "@/api/media";
import { postsService, postKeys } from "@/services/posts";
import { clubsService, clubKeys } from "@/services/clubs";
import { groupsService, groupKeys } from "@/services/groups";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { userLabel, fmtDateTime } from "@/utils/format";
import { renderPostBody } from "@/utils/postFormat";
import { smartSearch } from "@/utils/smartSearch";
import type { PostOwnerType, UUID } from "@/types";

interface PendingImage {
  imageId: UUID;
  previewUrl: string;
}

type MentionType = "user" | "club" | "group";
interface MentionCandidate {
  type: MentionType;
  id: UUID;
  label: string;
}

/** Match a `@query` still being typed right before the caret — used both to
 * open/filter the mention dropdown and, on selection, to know how much of
 * the text to replace. */
const MENTION_TRIGGER_RE = /@([^\s@]*)$/;

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
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: postKeys.list(ownerType, ownerId) });

  // --- @mentions: candidates are the post's own club/group members (visible
  // to whoever can already post here) plus every club/group name, mirroring
  // the same "search over already-loaded lists" pattern as EntitySearch —
  // there's no dedicated backend search endpoint for this. ---
  const clubs = useQuery({ queryKey: clubKeys.all, queryFn: clubsService.list });
  const groups = useQuery({ queryKey: groupKeys.all, queryFn: () => groupsService.list() });
  const clubMembers = useQuery({
    queryKey: clubKeys.members(ownerId),
    queryFn: () => clubsService.members(ownerId),
    enabled: ownerType === "club",
  });
  const groupDetail = useQuery({
    queryKey: groupKeys.detail(ownerId),
    queryFn: () => groupsService.get(ownerId),
    enabled: ownerType === "group",
  });

  const mentionCandidates = useMemo((): MentionCandidate[] => {
    const members = ownerType === "club" ? clubMembers.data : groupDetail.data?.members;
    return [
      ...(members ?? [])
        .filter((m) => m.user)
        .map((m): MentionCandidate => ({ type: "user", id: m.user_id, label: userLabel(m.user) })),
      ...(clubs.data ?? []).map((c): MentionCandidate => ({ type: "club", id: c.id, label: c.name })),
      ...(groups.data ?? []).map((g): MentionCandidate => ({ type: "group", id: g.id, label: g.name })),
    ];
  }, [ownerType, clubMembers.data, groupDetail.data, clubs.data, groups.data]);

  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [mentionStart, setMentionStart] = useState<number | null>(null);
  const [mentionActive, setMentionActive] = useState(0);
  const mentionResults =
    mentionQuery === null ? [] : smartSearch(mentionQuery, mentionCandidates, (c) => [c.label]).slice(0, 8);

  const closeMentions = () => {
    setMentionQuery(null);
    setMentionStart(null);
    setMentionActive(0);
  };

  const applyMention = (candidate: MentionCandidate) => {
    const el = textareaRef.current;
    if (!el || mentionStart === null) return;
    const caret = el.selectionStart;
    const token = `@[${candidate.label}](${candidate.type}:${candidate.id}) `;
    const next = body.slice(0, mentionStart) + token + body.slice(caret);
    setBody(next);
    closeMentions();
    requestAnimationFrame(() => {
      el.focus();
      const cursor = mentionStart + token.length;
      el.setSelectionRange(cursor, cursor);
    });
  };

  const handleBodyChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setBody(value);
    const caret = e.target.selectionStart;
    const match = MENTION_TRIGGER_RE.exec(value.slice(0, caret));
    if (match) {
      setMentionQuery(match[1]);
      setMentionStart(caret - match[1].length - 1);
      setMentionActive(0);
    } else {
      closeMentions();
    }
  };

  const handleBodyKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (mentionQuery === null || mentionResults.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setMentionActive((i) => (i + 1) % mentionResults.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setMentionActive((i) => (i - 1 + mentionResults.length) % mentionResults.length);
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      applyMention(mentionResults[mentionActive]);
    } else if (e.key === "Escape") {
      closeMentions();
    }
  };

  /** Wraps the current selection (or a placeholder, if nothing is selected)
   * in the given markers — used by the Bold/Italic/Underline toolbar
   * buttons. Re-selects the wrapped text afterwards so another click keeps
   * toggling the same span rather than appending markers each time. */
  const wrapSelection = (before: string, after: string = before) => {
    const el = textareaRef.current;
    if (!el) return;
    const { selectionStart, selectionEnd, value } = el;
    const selected = value.slice(selectionStart, selectionEnd) || t("gruppi.formatPlaceholder");
    const next = value.slice(0, selectionStart) + before + selected + after + value.slice(selectionEnd);
    setBody(next);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(selectionStart + before.length, selectionStart + before.length + selected.length);
    });
  };

  const insertLink = () => {
    const el = textareaRef.current;
    if (!el) return;
    const { selectionStart, selectionEnd, value } = el;
    const selected = value.slice(selectionStart, selectionEnd) || t("gruppi.linkLabelPlaceholder");
    const url = window.prompt(t("gruppi.linkUrlPrompt"));
    if (!url) return;
    const token = `[${selected}](${url})`;
    const next = value.slice(0, selectionStart) + token + value.slice(selectionEnd);
    setBody(next);
    requestAnimationFrame(() => {
      el.focus();
      const cursor = selectionStart + token.length;
      el.setSelectionRange(cursor, cursor);
    });
  };

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
      <div className="sf-feed-form__toolbar">
        <Button
          type="button"
          variant="ghost"
          className="sf-btn--icon-sm"
          aria-label={t("gruppi.formatBold")}
          onClick={() => wrapSelection("**")}
        >
          <Bold size={15} />
        </Button>
        <Button
          type="button"
          variant="ghost"
          className="sf-btn--icon-sm"
          aria-label={t("gruppi.formatItalic")}
          onClick={() => wrapSelection("*")}
        >
          <Italic size={15} />
        </Button>
        <Button
          type="button"
          variant="ghost"
          className="sf-btn--icon-sm"
          aria-label={t("gruppi.formatUnderline")}
          onClick={() => wrapSelection("__")}
        >
          <Underline size={15} />
        </Button>
        <Button
          type="button"
          variant="ghost"
          className="sf-btn--icon-sm"
          aria-label={t("gruppi.formatLink")}
          onClick={insertLink}
        >
          <Link2 size={15} />
        </Button>
      </div>
      <div className="sf-feed-form__field">
        <textarea
          ref={textareaRef}
          className="sf-field__input"
          id="feed-body"
          placeholder={t("gruppi.newsBody")}
          aria-label={t("gruppi.newsBody")}
          rows={3}
          value={body}
          onChange={handleBodyChange}
          onKeyDown={handleBodyKeyDown}
          onBlur={() => setTimeout(closeMentions, 150)}
          required
        />
        {mentionQuery !== null && mentionResults.length > 0 && (
          <div className="sf-feed-form__mentions">
            {mentionResults.map((c, i) => (
              <div
                key={`${c.type}-${c.id}`}
                className={`sf-feed-form__mention-option ${i === mentionActive ? "sf-feed-form__mention-option--active" : ""}`}
                onMouseDown={(e) => {
                  e.preventDefault();
                  applyMention(c);
                }}
              >
                <span>{c.label}</span>
                <span className="sf-feed-form__mention-type">{t(`gruppi.mentionType.${c.type}`)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
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
              <p className="sf-feed__post-body">{renderPostBody(p.body)}</p>
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
