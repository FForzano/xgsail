import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp } from "lucide-react";
import { boatsService, boatKeys } from "@/services/boats";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/api/client";
import { BackLink } from "@/components/ui/BackLink";
import { Section } from "@/components/ui/Section";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { InputField, TextAreaField } from "@/components/ui/InputField";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { fmtDateTime } from "@/utils/format";
import type { BoatNote, BoatSessionNote, UUID } from "@/types";
import styles from "./BoatNotebook.module.css";

/** Shared 403-vs-generic error message for both the notebook and logbook
 * queries — both hit boat-membership-gated endpoints the same way, only the
 * "members only" copy differs per section. */
function queryErrorMessage(error: unknown, membersOnlyKey: string, t: (key: string) => string): string {
  return error instanceof ApiError && error.status === 403 ? t(membersOnlyKey) : t("errors.generic");
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

  return (
    <div className="sf-section__body">
      <BackLink to={`/profilo/barche/${boatId}`} label={t("boatNotes.backToBoat")} />

      <Section
        title={t("boatNotes.title")}
        actions={
          manager && (
            <Button className="sf-btn--sm" onClick={openNew}>
              {t("boatNotes.new")}
            </Button>
          )
        }
      >
        {notes.isLoading ? (
          <Spinner />
        ) : notes.error ? (
          <p className="sf-muted">{queryErrorMessage(notes.error, "boatNotes.membersOnly", t)}</p>
        ) : !notes.data?.length ? (
          <p className="sf-muted">{t("boatNotes.empty")}</p>
        ) : (
          notes.data.map((note, i) => (
            <Card key={note.id} title={note.title}>
              <p className={styles.body}>{note.body}</p>
              {manager && (
                <div className={styles.actions}>
                  <div className={styles.moveGroup}>
                    <Button
                      variant="ghost"
                      className="sf-btn--sm"
                      aria-label={t("boatNotes.moveUp")}
                      disabled={i === 0 || reorder.isPending}
                      onClick={() => move(i, -1)}
                    >
                      <ChevronUp size={16} />
                    </Button>
                    <Button
                      variant="ghost"
                      className="sf-btn--sm"
                      aria-label={t("boatNotes.moveDown")}
                      disabled={i === notes.data.length - 1 || reorder.isPending}
                      onClick={() => move(i, 1)}
                    >
                      <ChevronDown size={16} />
                    </Button>
                  </div>
                  <Button variant="ghost" className="sf-btn--sm" onClick={() => openEdit(note)}>
                    {t("common.edit")}
                  </Button>
                  <Button variant="danger" className="sf-btn--sm" onClick={() => setDeleting(note)}>
                    {t("common.delete")}
                  </Button>
                </div>
              )}
            </Card>
          ))
        )}
      </Section>

      <Section title={t("boatLog.title")}>
        <p className="sf-muted">{t("boatLog.hint")}</p>
        {sessionNotes.isLoading ? (
          <Spinner />
        ) : sessionNotes.error ? (
          <p className="sf-muted">
            {queryErrorMessage(sessionNotes.error, "boatLog.membersOnly", t)}
          </p>
        ) : !sessionNotes.data?.length ? (
          <p className="sf-muted">{t("boatLog.empty")}</p>
        ) : (
          <ul className="sf-strip">
            {sessionNotes.data.map((note) => (
              <li key={note.session_id} className={`sf-strip__item ${styles.logRow}`}>
                <div className={styles.logMeta}>
                  <strong>{note.started_at ? fmtDateTime(note.started_at) : t("boatLog.noDate")}</strong>
                  <Link
                    className="sf-btn sf-btn--sm sf-btn--ghost"
                    to={`/diario/activities/${note.activity_id}/barche/${note.session_id}`}
                  >
                    {t("boatLog.openSession")}
                  </Link>
                </div>
                <p className={styles.body}>{note.notes}</p>
                {manager && (
                  <div className="sf-strip__actions">
                    <Button
                      variant="ghost"
                      className="sf-btn--sm"
                      onClick={() => openPromote(note)}
                    >
                      {t("boatLog.promote")}
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

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
