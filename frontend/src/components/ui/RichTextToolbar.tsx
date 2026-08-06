import { useState, type MouseEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  Bold,
  Heading1,
  Heading2,
  Heading3,
  Italic,
  Link2,
  Link2Off,
  List,
  ListOrdered,
  Table as TableIcon,
  Type,
  Underline,
} from "lucide-react";
import type { Editor } from "@tiptap/react";
import { useEditorState } from "@tiptap/react";
import { Popover } from "@/components/ui/Popover";
import { normalizeLinkHref } from "./richTextSchema";
import type { RichTextTier } from "./RichText";
import styles from "./RichText.module.css";

/** Toolbar labels live under a single `richText.*` namespace; every lookup
 * carries an English default so the component stays usable before (or if) a
 * locale file misses a key. */
function useLabels() {
  const { t } = useTranslation();
  return (key: string, fallback: string) => t(`richText.${key}`, { defaultValue: fallback });
}

/** Toolbar buttons must never take focus from ProseMirror: the browser blurs
 * the editor on mousedown, and a blurred editor has no selection left for the
 * command to act on. */
function keepEditorFocus(event: MouseEvent) {
  event.preventDefault();
}

function ToolButton({
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

function LinkForm({ editor, close }: { editor: Editor; close: () => void }) {
  const label = useLabels();
  const existing = (editor.getAttributes("link").href as string | undefined) ?? "";
  const [value, setValue] = useState(existing);
  const [invalid, setInvalid] = useState(false);

  const apply = () => {
    const href = normalizeLinkHref(value);
    if (!href) {
      setInvalid(true);
      return;
    }
    editor.chain().focus().extendMarkRange("link").setLink({ href }).run();
    close();
  };

  return (
    <div className={styles.linkForm}>
      <input
        className="sf-field__input"
        type="url"
        inputMode="url"
        autoFocus
        placeholder={label("linkPlaceholder", "https://example.com")}
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          setInvalid(false);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            apply();
          }
        }}
        aria-label={label("linkUrl", "Link URL")}
        aria-invalid={invalid}
      />
      {invalid && (
        <p className={styles.linkError}>
          {label("linkInvalid", "Enter an http, https or mailto address.")}
        </p>
      )}
      <div className={styles.linkActions}>
        <button type="button" className="sf-btn sf-btn--primary sf-btn--sm" onClick={apply}>
          {label("linkApply", "Apply")}
        </button>
        {existing && (
          <button
            type="button"
            className="sf-btn sf-btn--ghost sf-btn--sm"
            onClick={() => {
              editor.chain().focus().extendMarkRange("link").unsetLink().run();
              close();
            }}
          >
            <Link2Off size={15} /> {label("linkRemove", "Remove link")}
          </button>
        )}
      </div>
    </div>
  );
}

/** Reuses the global `sf-optionsmenu__*` chrome that `OptionsMenu` uses, so the
 * dropdowns here need no stylesheet of their own. `OptionsMenu` itself isn't
 * reused because its trigger is a hard-coded "⋮" with a non-translated label,
 * and these menus have to say what they open. */
function MenuPopover({
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

export function RichTextToolbar({ editor, tier }: { editor: Editor; tier: RichTextTier }) {
  const label = useLabels();
  const full = tier === "full";

  // Tiptap 3 does not re-render on every transaction, so active states have to
  // be pulled through `useEditorState` or the toolbar goes stale.
  const state = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      bold: e.isActive("bold"),
      italic: e.isActive("italic"),
      underline: e.isActive("underline"),
      link: e.isActive("link"),
      h1: e.isActive("heading", { level: 1 }),
      h2: e.isActive("heading", { level: 2 }),
      h3: e.isActive("heading", { level: 3 }),
      bulletList: e.isActive("bulletList"),
      orderedList: e.isActive("orderedList"),
      inTable: e.isActive("table"),
    }),
  });

  const headingLabel = state.h1
    ? label("heading1", "Heading 1")
    : state.h2
      ? label("heading2", "Heading 2")
      : state.h3
        ? label("heading3", "Heading 3")
        : label("paragraph", "Paragraph");

  return (
    <div className={styles.toolbar} role="toolbar" aria-label={label("toolbar", "Formatting")}>
      <div className={styles.toolGroup}>
        <ToolButton
          label={label("bold", "Bold")}
          icon={<Bold size={17} />}
          active={state.bold}
          onClick={() => editor.chain().focus().toggleBold().run()}
        />
        <ToolButton
          label={label("italic", "Italic")}
          icon={<Italic size={17} />}
          active={state.italic}
          onClick={() => editor.chain().focus().toggleItalic().run()}
        />
        <ToolButton
          label={label("underline", "Underline")}
          icon={<Underline size={17} />}
          active={state.underline}
          onClick={() => editor.chain().focus().toggleUnderline().run()}
        />
        <Popover
          panelClassName={styles.linkPanel}
          trigger={({ open, toggle }) => (
            <ToolButton
              label={label("link", "Link")}
              icon={<Link2 size={17} />}
              active={state.link}
              expanded={open}
              onClick={toggle}
            />
          )}
        >
          {({ close }) => <LinkForm editor={editor} close={close} />}
        </Popover>
      </div>

      {full && (
        <div className={styles.toolGroup}>
          <MenuPopover
            trigger={({ open, toggle }) => (
              <ToolButton
                label={`${label("style", "Text style")}: ${headingLabel}`}
                icon={
                  state.h1 ? (
                    <Heading1 size={17} />
                  ) : state.h2 ? (
                    <Heading2 size={17} />
                  ) : state.h3 ? (
                    <Heading3 size={17} />
                  ) : (
                    <Type size={17} />
                  )
                }
                active={state.h1 || state.h2 || state.h3}
                expanded={open}
                onClick={toggle}
              />
            )}
            items={[
              {
                label: label("paragraph", "Paragraph"),
                active: !state.h1 && !state.h2 && !state.h3,
                onClick: () => editor.chain().focus().setParagraph().run(),
              },
              {
                label: label("heading1", "Heading 1"),
                active: state.h1,
                onClick: () => editor.chain().focus().toggleHeading({ level: 1 }).run(),
              },
              {
                label: label("heading2", "Heading 2"),
                active: state.h2,
                onClick: () => editor.chain().focus().toggleHeading({ level: 2 }).run(),
              },
              {
                label: label("heading3", "Heading 3"),
                active: state.h3,
                onClick: () => editor.chain().focus().toggleHeading({ level: 3 }).run(),
              },
            ]}
          />
          <ToolButton
            label={label("bulletList", "Bulleted list")}
            icon={<List size={17} />}
            active={state.bulletList}
            onClick={() => editor.chain().focus().toggleBulletList().run()}
          />
          <ToolButton
            label={label("orderedList", "Numbered list")}
            icon={<ListOrdered size={17} />}
            active={state.orderedList}
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
          />
          {state.inTable ? (
            // Eight permanently-visible table buttons are unusable on a phone,
            // so they only exist while the caret is actually inside a table.
            <MenuPopover
              trigger={({ open, toggle }) => (
                <ToolButton
                  label={label("tableOptions", "Table options")}
                  icon={<TableIcon size={17} />}
                  active
                  expanded={open}
                  onClick={toggle}
                />
              )}
              items={[
                {
                  label: label("addRow", "Insert row"),
                  onClick: () => editor.chain().focus().addRowAfter().run(),
                },
                {
                  label: label("deleteRow", "Delete row"),
                  onClick: () => editor.chain().focus().deleteRow().run(),
                },
                {
                  label: label("addColumn", "Insert column"),
                  onClick: () => editor.chain().focus().addColumnAfter().run(),
                },
                {
                  label: label("deleteColumn", "Delete column"),
                  onClick: () => editor.chain().focus().deleteColumn().run(),
                },
                {
                  label: label("deleteTable", "Delete table"),
                  danger: true,
                  onClick: () => editor.chain().focus().deleteTable().run(),
                },
              ]}
            />
          ) : (
            <ToolButton
              label={label("insertTable", "Insert table")}
              icon={<TableIcon size={17} />}
              onClick={() =>
                editor
                  .chain()
                  .focus()
                  .insertTable({ rows: 3, cols: 3, withHeaderRow: true })
                  .run()
              }
            />
          )}
        </div>
      )}
    </div>
  );
}
