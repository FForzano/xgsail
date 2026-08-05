import { useLayoutEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookmarkPlus,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  NotebookText,
  Pencil,
  ScrollText,
  Trash2,
} from "lucide-react";
import { boatsService, boatKeys } from "@/services/boats";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useToast } from "@/hooks/useToast";
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

  return (
    <>
      <div className={`${styles.bodyWrap} ${overflows && !expanded ? styles.faded : ""}`}>
        <p ref={ref} className={`${styles.body} ${expanded ? "" : styles.clamped}`}>
          {text}
        </p>
      </div>
      {overflows && (
        <Button
          variant="ghost"
          className={`sf-btn--sm ${styles.toggle}`}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {expanded ? t("common.collapse") : t("common.expand")}
        </Button>
      )}
    </>
  );
}

export function BoatNotebookPage() {
  const { boatId } = useParams<{ boatId: UUID }>();
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

  const sessionNotes = useQuery({
    queryKey: boatKeys.sessionNotes(boatId!),
    queryFn: () => boatsService.sessionNotes(boatId!),
    enabled: !!boatId,
    retry: false,
  });

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
    { id: "log" as const, label: t("boatLog.tabShort"), Icon: ScrollText, count: sessionNotes.data?.length },
  ];

  return (
    <div className="sf-section__body">
      <BackLink to={`/profilo/barche/${boatId}`} label={t("boatNotes.backToBoat")} />

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
            {sessionNotes.isLoading ? (
              <Spinner />
            ) : sessionNotes.error ? (
              <p className="sf-muted">
                {queryErrorMessage(sessionNotes.error, "boatLog.membersOnly", t)}
              </p>
            ) : !sessionNotes.data?.length ? (
              <p className="sf-muted">{t("boatLog.empty")}</p>
            ) : (
              <ul className={styles.stack}>
                {sessionNotes.data.map((note) => (
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
                            <BookmarkPlus size={15} />
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
