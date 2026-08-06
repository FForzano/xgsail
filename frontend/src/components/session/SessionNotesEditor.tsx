import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { LayoutTemplate, Lock, Users } from "lucide-react";
import { noteTemplatesService, noteTemplateKeys } from "@/services/noteTemplates";
import { RichTextField } from "@/components/ui/RichTextField";
import { MenuPopover, ToolButton, useLabels } from "@/components/ui/richTextToolbarControls";
import styles from "@/components/ui/RichText.module.css";

/** The `sessions.notes` editor shared by `SessionDetail` and the boat
 * logbook: same field (notes + notes_shared), same template picker, so it
 * exists once instead of twice. Its toolbar's leading/trailing slots (see
 * `RichTextField`) hold the template picker and the share toggle — moved off
 * the standalone `<select>` and checkbox that used to sit above/below the
 * editor, to give the body the whole modal instead of splitting it three ways. */
export function SessionNotesEditor({
  id,
  value,
  onChange,
  shared,
  onSharedChange,
  onManageTemplates,
}: {
  id: string;
  value: string;
  onChange: (html: string) => void;
  shared: boolean;
  onSharedChange: (shared: boolean) => void;
  /** Navigates to the templates manager — the caller closes its own modal
   * first, since leaving the page with it still open makes no sense. */
  onManageTemplates: () => void;
}) {
  const { t } = useTranslation();
  const label = useLabels();
  const templates = useQuery({ queryKey: noteTemplateKeys.mine, queryFn: noteTemplatesService.listMine });

  const templateItems = [
    ...(templates.data ?? []).map((tpl) => ({
      label: tpl.name,
      onClick: () => onChange(tpl.body),
    })),
    { label: t("noteTemplates.manage"), onClick: onManageTemplates },
  ];

  return (
    <RichTextField
      label={t("sessions.notes")}
      id={id}
      tier="full"
      fill
      placeholder={t("sessions.notesPlaceholder")}
      value={value}
      onChange={onChange}
      leadingToolbarItems={
        <MenuPopover
          trigger={({ open, toggle }) => (
            <ToolButton
              label={label("templates", "Apply a template")}
              icon={<LayoutTemplate size={17} />}
              expanded={open}
              onClick={toggle}
            />
          )}
          items={templateItems}
        />
      }
      trailingToolbarItems={
        <button
          type="button"
          className={`${styles.toolBtn} ${styles.toolBtnLabeled} ${shared ? styles.toolBtnActive : ""}`}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => onSharedChange(!shared)}
          aria-pressed={shared}
          title={t("sessions.notesSharedHint")}
        >
          {shared ? <Users size={16} /> : <Lock size={16} />}
          <span>{shared ? label("shared", "Shared") : label("private", "Private")}</span>
        </button>
      }
    />
  );
}
