import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { noteTemplatesService, noteTemplateKeys } from "@/services/noteTemplates";
import { useAutoSaveOnClose } from "@/hooks/useAutoSaveOnClose";
import { Button } from "@/components/ui/Button";
import { RichTextField } from "@/components/ui/RichTextField";
import { Modal } from "@/components/ui/Modal";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { richTextExcerpt } from "@/utils/richTextExcerpt";
import type { NoteTemplate, UUID } from "@/types";

/** Personal reusable snippets to prefill the session-notes editor (see
 * SessionNotesEditor.tsx). Prop-less by design so both the Barche sub-page
 * and the notes editor's modal mount the exact same UI. */
export function NoteTemplatesManager({ className }: { className?: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const templates = useQuery({ queryKey: noteTemplateKeys.mine, queryFn: noteTemplatesService.listMine });
  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [editingTemplateId, setEditingTemplateId] = useState<UUID | null>(null);
  const [templateForm, setTemplateForm] = useState({ name: "", body: "" });
  const originalTemplateFormRef = useRef(templateForm);
  const [deleting, setDeleting] = useState<NoteTemplate | null>(null);

  const openNewTemplate = () => {
    setEditingTemplateId(null);
    const next = { name: "", body: "" };
    setTemplateForm(next);
    originalTemplateFormRef.current = next;
    setTemplateModalOpen(true);
  };
  const openEditTemplate = (tpl: NoteTemplate) => {
    setEditingTemplateId(tpl.id);
    const next = { name: tpl.name, body: tpl.body };
    setTemplateForm(next);
    originalTemplateFormRef.current = next;
    setTemplateModalOpen(true);
  };

  const saveTemplate = useMutation({
    mutationFn: () =>
      editingTemplateId
        ? noteTemplatesService.update(editingTemplateId, templateForm)
        : noteTemplatesService.create(templateForm),
    onSuccess: async (result) => {
      if (!editingTemplateId) setEditingTemplateId(result.id);
      originalTemplateFormRef.current = templateForm;
      await queryClient.invalidateQueries({ queryKey: noteTemplateKeys.mine });
    },
    // No onError here: `useAutoSaveOnClose` below owns surfacing a save
    // failure (on close) or retrying silently (periodic).
  });
  const { requestClose: requestCloseTemplate } = useAutoSaveOnClose({
    canSave: () => templateForm.name.trim() !== "" && richTextExcerpt(templateForm.body, 1) !== "",
    isDirty: () =>
      templateForm.name !== originalTemplateFormRef.current.name ||
      templateForm.body !== originalTemplateFormRef.current.body,
    save: () => saveTemplate.mutateAsync(),
    onClosed: () => setTemplateModalOpen(false),
  });
  const removeTemplate = useMutation({
    mutationFn: (id: UUID) => noteTemplatesService.remove(id),
    onSuccess: async () => {
      setDeleting(null);
      await queryClient.invalidateQueries({ queryKey: noteTemplateKeys.mine });
    },
  });

  return (
    <div className={className}>
      <p className="sf-muted">{t("noteTemplates.hint")}</p>
      <div className="sf-toolbar" style={{ justifyContent: "flex-end" }}>
        <Button className="sf-btn--sm" onClick={openNewTemplate}>
          {t("noteTemplates.new")}
        </Button>
      </div>
      {templates.data?.length ? (
        <div className="sf-strip">
          {templates.data.map((tpl) => (
            <div key={tpl.id} className="sf-strip__item sf-strip__item--muted">
              <span>
                <strong>{tpl.name}</strong> <span className="sf-muted">{richTextExcerpt(tpl.body, 60)}</span>
              </span>
              <span className="sf-strip__actions">
                <Button
                  variant="ghost"
                  className="sf-btn--icon-sm"
                  aria-label={t("common.edit")}
                  title={t("common.edit")}
                  onClick={() => openEditTemplate(tpl)}
                >
                  <Pencil size={15} />
                </Button>
                <Button
                  variant="ghost"
                  className="sf-btn--icon-sm sf-btn--icon-danger"
                  aria-label={t("common.delete")}
                  title={t("common.delete")}
                  onClick={() => setDeleting(tpl)}
                >
                  <Trash2 size={15} />
                </Button>
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="sf-muted">{t("noteTemplates.empty")}</p>
      )}
      {templateModalOpen && (
        <Modal
          title={editingTemplateId ? t("noteTemplates.edit") : t("noteTemplates.new")}
          onClose={requestCloseTemplate}
          size="wide"
          fillBody
        >
          <RichTextField
            label={t("noteTemplates.name")}
            id="template-body"
            tier="full"
            fill
            title={templateForm.name}
            onTitleChange={(name) => setTemplateForm((f) => ({ ...f, name }))}
            titlePlaceholder={t("noteTemplates.name")}
            value={templateForm.body}
            onChange={(html) => setTemplateForm((f) => ({ ...f, body: html }))}
          />
        </Modal>
      )}
      {deleting && (
        <ConfirmDialog
          title={t("common.delete")}
          message={t("noteTemplates.deleteConfirm")}
          busy={removeTemplate.isPending}
          onConfirm={() => removeTemplate.mutate(deleting.id)}
          onClose={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
