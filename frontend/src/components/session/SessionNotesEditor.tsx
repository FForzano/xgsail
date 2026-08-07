import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { LayoutTemplate, Lock, Users } from "lucide-react";
import { noteTemplatesService, noteTemplateKeys } from "@/services/noteTemplates";
import { RichTextField } from "@/components/ui/RichTextField";
import { Modal } from "@/components/ui/Modal";
import { NoteTemplatesManager } from "@/components/notes/NoteTemplatesManager";
import { keepEditorFocus, MenuPopover, useLabels } from "@/components/ui/richTextToolbarControls";
import styles from "@/components/ui/RichText.module.css";

/** Icon-over-caption, not icon-only: neither the template icon nor a bare
 * lock/people icon reads as self-explanatory the first time, so both of
 * these leading buttons carry a permanent one-word label instead of relying
 * on a hover tooltip to explain themselves. */
function StackedToolButton({
  icon,
  caption,
  ariaLabel,
  active,
  expanded,
  onClick,
}: {
  icon: React.ReactNode;
  caption: string;
  ariaLabel: string;
  active?: boolean;
  expanded?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`${styles.toolBtn} ${styles.toolBtnStacked} ${active ? styles.toolBtnActive : ""}`}
      aria-label={ariaLabel}
      title={ariaLabel}
      aria-pressed={expanded === undefined ? active : undefined}
      aria-expanded={expanded}
      onMouseDown={keepEditorFocus}
      onClick={onClick}
    >
      {icon}
      <span className={styles.toolBtnStackedLabel}>{caption}</span>
    </button>
  );
}

/** The `sessions.notes` editor shared by `SessionDetail` and the boat
 * logbook: same field (notes + notes_shared), same template picker, so it
 * exists once instead of twice. The template picker and share toggle are
 * both leading toolbar items (see `RichTextField`) — first, ahead of a
 * divider from the text-formatting groups — replacing the standalone
 * `<select>` and checkbox that used to sit above/below the editor, to give
 * the body the whole modal instead of splitting it three ways. */
export function SessionNotesEditor({
  id,
  value,
  onChange,
  shared,
  onSharedChange,
}: {
  id: string;
  value: string;
  onChange: (html: string) => void;
  shared: boolean;
  onSharedChange: (shared: boolean) => void;
}) {
  const { t } = useTranslation();
  const label = useLabels();
  const templates = useQuery({ queryKey: noteTemplateKeys.mine, queryFn: noteTemplatesService.listMine });
  // Managed in place rather than by navigating to the templates page: leaving
  // the editor would throw away the note being written.
  const [managing, setManaging] = useState(false);

  const templateItems = [
    ...(templates.data ?? []).map((tpl) => ({
      label: tpl.name,
      onClick: () => onChange(tpl.body),
    })),
    { label: t("noteTemplates.manage"), onClick: () => setManaging(true) },
  ];

  return (
    <>
      <RichTextField
        label={t("sessions.notes")}
        id={id}
        tier="full"
        fill
        placeholder={t("sessions.notesPlaceholder")}
        value={value}
        onChange={onChange}
        leadingToolbarItems={
          <>
            <MenuPopover
              panelClassName={styles.toolbarLeadingMenu}
              trigger={({ open, toggle }) => (
                <StackedToolButton
                  icon={<LayoutTemplate size={17} />}
                  caption={label("templatesShort", "Templates")}
                  ariaLabel={label("templates", "Apply a template")}
                  expanded={open}
                  onClick={toggle}
                />
              )}
              items={templateItems}
            />
            <StackedToolButton
              icon={shared ? <Users size={16} /> : <Lock size={16} />}
              caption={shared ? label("shared", "Shared") : label("private", "Private")}
              ariaLabel={t("sessions.notesSharedHint")}
              active={shared}
              onClick={() => onSharedChange(!shared)}
            />
          </>
        }
      />
      {managing && (
        <Modal title={t("noteTemplates.title")} onClose={() => setManaging(false)} size="wide">
          <NoteTemplatesManager />
        </Modal>
      )}
    </>
  );
}
