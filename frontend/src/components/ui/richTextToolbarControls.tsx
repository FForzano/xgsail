import type { MouseEvent, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Popover } from "@/components/ui/Popover";
import styles from "./RichText.module.css";

/** Pure toolbar-button chrome, deliberately kept free of any `@tiptap/*`
 * import: `RichTextToolbar.tsx` (the lazy-loaded editor chunk) uses these,
 * but so does `SessionNotesEditor.tsx` — which is part of the *eager* bundle
 * (`SessionDetail`/`BoatNotebookPage` render it outside any `<Suspense>`
 * boundary). Importing these from `RichTextToolbar.tsx` instead would drag
 * ProseMirror into the eager chunk along with them. */

/** Toolbar labels live under a single `richText.*` namespace; every lookup
 * carries an English default so the component stays usable before (or if) a
 * locale file misses a key. */
export function useLabels() {
  const { t } = useTranslation();
  return (key: string, fallback: string) => t(`richText.${key}`, { defaultValue: fallback });
}

/** Toolbar buttons must never take focus from ProseMirror: the browser blurs
 * the editor on mousedown, and a blurred editor has no selection left for the
 * command to act on. */
export function keepEditorFocus(event: MouseEvent) {
  event.preventDefault();
}

export function ToolButton({
  label,
  icon,
  active,
  disabled,
  onClick,
  expanded,
}: {
  label: string;
  icon: ReactNode;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
  expanded?: boolean;
}) {
  return (
    <button
      type="button"
      className={`${styles.toolBtn} ${active ? styles.toolBtnActive : ""}`}
      aria-label={label}
      title={label}
      aria-pressed={expanded === undefined ? active : undefined}
      aria-expanded={expanded}
      disabled={disabled}
      onMouseDown={keepEditorFocus}
      onClick={onClick}
    >
      {icon}
    </button>
  );
}

/** Reuses the global `sf-optionsmenu__*` chrome that `OptionsMenu` uses, so the
 * dropdowns here need no stylesheet of their own. `OptionsMenu` itself isn't
 * reused because its trigger is a hard-coded "⋮" with a non-translated label,
 * and these menus have to say what they open. */
export function MenuPopover({
  trigger,
  items,
}: {
  trigger: (state: { open: boolean; toggle: () => void }) => ReactNode;
  items: { label: string; onClick: () => void; active?: boolean; danger?: boolean }[];
}) {
  return (
    <Popover panelClassName="sf-optionsmenu__panel" trigger={trigger}>
      {({ close }) =>
        items.map((item, i) => (
          <button
            key={i}
            type="button"
            role="menuitem"
            aria-current={item.active || undefined}
            className={`sf-optionsmenu__item ${item.danger ? "sf-optionsmenu__item--danger" : ""} ${
              item.active ? styles.menuItemActive : ""
            }`}
            onMouseDown={keepEditorFocus}
            onClick={() => {
              close();
              item.onClick();
            }}
          >
            {item.label}
          </button>
        ))
      }
    </Popover>
  );
}
