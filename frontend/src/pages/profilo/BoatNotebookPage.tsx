import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  NotebookPen,
  NotebookText,
  Pencil,
  ScrollText,
  Search,
  Trash2,
} from "lucide-react";
import { boatsService, boatKeys } from "@/services/boats";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useToast } from "@/hooks/useToast";
import { useInfiniteScrollSentinel } from "@/hooks/useInfiniteScrollSentinel";
import { ApiError } from "@/api/client";
import { BackLink } from "@/components/ui/BackLink";
import { Section } from "@/components/ui/Section";
import { Button } from "@/components/ui/Button";
import { InputField, TextAreaField } from "@/components/ui/InputField";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { fmtDateTime } from "@/utils/format";
import type { BoatNote, BoatSessionNote, UUID } from "@/types";
import styles from "./BoatNotebook.module.css";

type Tab = "notebook" | "log";
const LOG_PAGE_SIZE = 20;
const LOG_SEARCH_DEBOUNCE_MS = 300;

const ICON_BTN = "sf-btn sf-btn--ghost sf-btn--icon-sm";

/** Shared 403-vs-generic error message for both the notebook and logbook
 * queries — both hit boat-membership-gated endpoints the same way, only the
 * "members only" copy differs per section. */
function queryErrorMessage(error: unknown, membersOnlyKey: string, t: (key: string) => string): string {
  return error instanceof ApiError && error.status === 403 ? t(membersOnlyKey) : t("errors.generic");
}

/** Note text clamped to a readable height, with the expand toggle shown only
 * when the text really overflows — measured rather than assumed, so a two-line
 * note gets no pointless button. */
function NoteBody({ text }: { text: string }) {
  const { t } = useTranslation();
  const ref = useRef<HTMLParagraphElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);

  useLayoutEffect(() => {
    const el = ref.current;
    // Only the clamped element can be measured; expanding it would read as "fits".
    if (!el || expanded) return;
    setOverflows(el.scrollHeight > el.clientHeight + 1);
  }, [text, expanded]);

  const toggle = () => overflows && setExpanded((v) => !v);

  return (
    <>
      <div className={`${styles.bodyWrap} ${overflows && !expanded ? styles.faded : ""}`}>
        <p
          ref={ref}
          className={`${styles.body} ${expanded ? "" : styles.clamped} ${overflows ? styles.tappable : ""}`}
          role={overflows ? "button" : undefined}
          tabIndex={overflows ? 0 : undefined}
          aria-expanded={overflows ? expanded : undefined}
          onClick={toggle}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              toggle();
            }
          }}
        >
          {text}
        </p>
      </div>
      {overflows && (
        <Button variant="ghost" className={`sf-btn--sm ${styles.toggle}`} onClick={toggle}>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {expanded ? t("common.collapse") : t("common.expand")}
        </Button>
      )}
    </>
  );
}

export function BoatNotebookPage() {
  const { boatId } = useParams<{ boatId: UUID }>();
  const location = useLocation();
  // `fallback` below falls back to the boat page only when there's no
  // history to unwind — the same case where "Torna alla barca" is accurate.
  // When we arrived from elsewhere (a session's quick action), that caller
  // hands us the right label via router state instead of guessing here.
  const backLabel = (location.state as { backLabel?: string } | null)?.backLabel;
  const { t } = useTranslation();
  const { isBoatManager } = useCapabilities();
  const { notify } = useToast();
  const queryClient = useQueryClient();

  const notes = useQuery({
    queryKey: boatKeys.notes(boatId!),
    queryFn: () => boatsService.notes(boatId!),
    enabled: !!boatId,
    retry: false,
  });

  const [logQuery, setLogQuery] = useState("");
  const [logQueryDebounced, setLogQueryDebounced] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setLogQueryDebounced(logQuery.trim()), LOG_SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [logQuery]);

  const sessionNotes = useInfiniteQuery({
    queryKey: boatKeys.sessionNotes(boatId!, logQueryDebounced),
    queryFn: ({ pageParam }) =>
      boatsService.sessionNotes(boatId!, {
        limit: LOG_PAGE_SIZE,
        offset: pageParam,
        q: logQueryDebounced || undefined,
      }),
    initialPageParam: 0,
    // The endpoint doesn't return a total count — a page shorter than
    // LOG_PAGE_SIZE means we've reached the end. Same convention as
    // useDiaryFeed's activities pagination (see its own comment): the
    // per-row visibility filter runs server-side after the SQL limit, so
    // this is a slight over-simplification there too, accepted for
    // consistency rather than inventing a different contract here.
    getNextPageParam: (lastPage, allPages) =>
      lastPage.length < LOG_PAGE_SIZE ? undefined : allPages.length * LOG_PAGE_SIZE,
    enabled: !!boatId,
    retry: false,
  });
  const sessionNoteList = useMemo(
    () => sessionNotes.data?.pages.flat() ?? [],
    [sessionNotes.data],
  );
  const sessionNotesSentinelRef = useInfiniteScrollSentinel<HTMLDivElement>(
    () => sessionNotes.fetchNextPage(),
    sessionNotes.hasNextPage === true && !sessionNotes.isFetchingNextPage,
  );

  const [tab, setTab] = useState<Tab>("notebook");
  const [editing, setEditing] = useState<BoatNote | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ title: "", body: "" });
  const [deleting, setDeleting] = useState<BoatNote | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: boatKeys.notes(boatId!) });

  const save = useMutation({
    mutationFn: () =>
      editing
        ? boatsService.updateNote(boatId!, editing.id, form)
        : boatsService.createNote(boatId!, form),
    onSuccess: async () => {
      setCreating(false);
      setEditing(null);
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  const remove = useMutation({
    mutationFn: (note: BoatNote) => boatsService.removeNote(boatId!, note.id),
    onSuccess: async () => {
      setDeleting(null);
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  const reorder = useMutation({
    mutationFn: (noteIds: UUID[]) => boatsService.reorderNotes(boatId!, noteIds),
    onSuccess: async () => {
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  const openPrefilled = (title: string, body: string) => {
    setEditing(null);
    setForm({ title, body });
    setCreating(true);
  };
  const openNew = () => openPrefilled("", "");
  const openEdit = (note: BoatNote) => {
    setEditing(note);
    setForm({ title: note.title, body: note.body });
    setCreating(true);
  };
  const openPromote = (note: BoatSessionNote) => {
    const title = note.started_at ? fmtDateTime(note.started_at) : t("boatLog.promotedTitle");
    openPrefilled(title, note.notes);
  };

  const move = (index: number, direction: -1 | 1) => {
    const list = notes.data;
    if (!list) return;
    const target = index + direction;
    if (target < 0 || target >= list.length) return;
    const reordered = [...list];
    [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
    reorder.mutate(reordered.map((n) => n.id));
  };

  const manager = !!boatId && isBoatManager(boatId);

  const tabs = [
    { id: "notebook" as const, label: t("boatNotes.tabShort"), Icon: NotebookText, count: notes.data?.length },
    // No count badge here: with pagination, `sessionNoteList.length` is only
    // "loaded so far," not the true total, and showing it as if it were the
    // total would misrepresent it (unlike the notebook tab, which has none).
    { id: "log" as const, label: t("boatLog.tabShort"), Icon: ScrollText, count: undefined },
  ];

  return (
    <div className="sf-section__body">
      <BackLink fallback={`/profilo/barche/${boatId}`} label={backLabel ?? t("boatNotes.backToBoat")} />

      <div className={styles.switch} role="tablist" aria-label={t("boatNotes.title")}>
        <span
          className={styles.switchThumb}
          data-index={tabs.findIndex((x) => x.id === tab)}
          aria-hidden="true"
        />
        {tabs.map(({ id, label, Icon, count }) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`boat-nb-tab-${id}`}
            aria-controls={`boat-nb-panel-${id}`}
            aria-selected={tab === id}
            className={styles.switchOption}
            onClick={() => setTab(id)}
          >
            <Icon size={15} />
            {label}
            {count !== undefined && <span className={styles.switchCount}>{count}</span>}
          </button>
        ))}
      </div>

      {tab === "notebook" ? (
        <Section
          className={styles.panel}
          actions={
            manager && (
              <Button className="sf-btn--sm" onClick={openNew}>
                {t("boatNotes.new")}
              </Button>
            )
          }
        >
          <div
            className={styles.tabPanel}
            role="tabpanel"
            id="boat-nb-panel-notebook"
            aria-labelledby="boat-nb-tab-notebook"
          >
            <p className={`sf-muted ${styles.hint}`}>{t("boatNotes.hint")}</p>
            {notes.isLoading ? (
              <Spinner />
            ) : notes.error ? (
              <p className="sf-muted">{queryErrorMessage(notes.error, "boatNotes.membersOnly", t)}</p>
            ) : !notes.data?.length ? (
              <p className="sf-muted">{t("boatNotes.empty")}</p>
            ) : (
              <ul className={styles.stack}>
                {notes.data.map((note, i) => (
                  <li key={note.id} className={styles.note}>
                    <div className={styles.noteHead}>
                      <h3 className={styles.noteTitle}>{note.title}</h3>
                    </div>
                    <NoteBody text={note.body} />
                    {manager && (
                      <div className={styles.noteFoot}>
                        <div className={styles.moveGroup}>
                          <Button
                            variant="ghost"
                            className="sf-btn--icon-sm"
                            aria-label={t("boatNotes.moveUp")}
                            title={t("boatNotes.moveUp")}
                            disabled={i === 0 || reorder.isPending}
                            onClick={() => move(i, -1)}
                          >
                            <ChevronUp size={16} />
                          </Button>
                          <Button
                            variant="ghost"
                            className="sf-btn--icon-sm"
                            aria-label={t("boatNotes.moveDown")}
                            title={t("boatNotes.moveDown")}
                            disabled={i === notes.data.length - 1 || reorder.isPending}
                            onClick={() => move(i, 1)}
                          >
                            <ChevronDown size={16} />
                          </Button>
                        </div>
                        <Button
                          variant="ghost"
                          className="sf-btn--icon-sm"
                          aria-label={t("common.edit")}
                          title={t("common.edit")}
                          onClick={() => openEdit(note)}
                        >
                          <Pencil size={15} />
                        </Button>
                        <Button
                          variant="ghost"
                          className={`sf-btn--icon-sm ${styles.dangerIcon}`}
                          aria-label={t("common.delete")}
                          title={t("common.delete")}
                          onClick={() => setDeleting(note)}
                        >
                          <Trash2 size={15} />
                        </Button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Section>
      ) : (
        <Section className={styles.panel}>
          <div
            className={styles.tabPanel}
            role="tabpanel"
            id="boat-nb-panel-log"
            aria-labelledby="boat-nb-tab-log"
          >
            <p className={`sf-muted ${styles.hint}`}>{t("boatLog.hint")}</p>
            <div className={styles.logSearch}>
              <Search size={15} aria-hidden />
              <input
                type="text"
                className={styles.logSearchInput}
                placeholder={t("boatLog.searchPlaceholder")}
                value={logQuery}
                onChange={(e) => setLogQuery(e.target.value)}
                aria-label={t("boatLog.searchPlaceholder")}
              />
            </div>
            {sessionNotes.isLoading ? (
              <Spinner />
            ) : sessionNotes.error ? (
              <p className="sf-muted">
                {queryErrorMessage(sessionNotes.error, "boatLog.membersOnly", t)}
              </p>
            ) : !sessionNoteList.length ? (
              <p className="sf-muted">
                {logQueryDebounced ? t("boatLog.noSearchResults") : t("boatLog.empty")}
              </p>
            ) : (
              <ul className={styles.stack}>
                {sessionNoteList.map((note) => (
                  <li key={note.session_id} className={`${styles.note} ${styles.noteLog}`}>
                    <div className={styles.noteHead}>
                      <span className={styles.noteDate}>
                        {note.started_at ? fmtDateTime(note.started_at) : t("boatLog.noDate")}
                      </span>
                      <div className={styles.noteTools}>
                        {manager && (
                          <Button
                            variant="ghost"
                            className="sf-btn--icon-sm"
                            aria-label={t("boatLog.promote")}
                            title={t("boatLog.promote")}
                            onClick={() => openPromote(note)}
                          >
                            <NotebookPen size={15} />
                          </Button>
                        )}
                        <Link
                          className={ICON_BTN}
                          aria-label={t("boatLog.openSession")}
                          title={t("boatLog.openSession")}
                          to={`/diario/activities/${note.activity_id}/barche/${note.session_id}`}
                        >
                          <ExternalLink size={15} />
                        </Link>
                      </div>
                    </div>
                    <NoteBody text={note.notes} />
                  </li>
                ))}
              </ul>
            )}
            {sessionNotes.hasNextPage && (
              <div ref={sessionNotesSentinelRef} className={styles.logSentinel}>
                <Spinner inline />
              </div>
            )}
          </div>
        </Section>
      )}

      {creating && (
        <Modal title={editing ? t("boatNotes.edit") : t("boatNotes.new")} onClose={() => setCreating(false)}>
          <InputField
            label={t("boatNotes.entryTitle")}
            id="note-title"
            value={form.title}
            onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
          />
          <TextAreaField
            label={t("boatNotes.body")}
            id="note-body"
            rows={6}
            value={form.body}
            onChange={(e) => setForm((f) => ({ ...f, body: e.target.value }))}
          />
          <div className="sf-form__actions">
            <Button
              onClick={() => save.mutate()}
              disabled={save.isPending || !form.title.trim() || !form.body.trim()}
            >
              {t("common.save")}
            </Button>
          </div>
        </Modal>
      )}

      {deleting && (
        <ConfirmDialog
          title={t("common.delete")}
          message={t("boatNotes.deleteConfirm")}
          busy={remove.isPending}
          onConfirm={() => remove.mutate(deleting)}
          onClose={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
