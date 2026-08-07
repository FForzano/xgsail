import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  Bold,
  ChevronLeft,
  ChevronRight,
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
import { keepEditorFocus, MenuPopover, ToolButton, useLabels } from "@/components/ui/richTextToolbarControls";
import { normalizeLinkHref } from "./richTextSchema";
import type { RichTextTier } from "./RichText";
import styles from "./RichText.module.css";

/** The toolbar is one non-wrapping scrollable row now (was two wrapped rows);
 * this tracks whether there's more content off-screen on either side so the
 * nav chevrons only show up when they'd actually do something. */
function useToolbarScroll() {
  const ref = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const update = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 1);
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    update();
    el.addEventListener("scroll", update, { passive: true });
    const resizeObserver = new ResizeObserver(update);
    resizeObserver.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      resizeObserver.disconnect();
    };
    // `update` is stable (empty deps), so this only needs to run once per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const scrollBy = (delta: number) => ref.current?.scrollBy({ left: delta, behavior: "smooth" });

  return { ref, canScrollLeft, canScrollRight, scrollBy };
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


export function RichTextToolbar({
  editor,
  tier,
  leadingItems,
  trailingItems,
}: {
  editor: Editor;
  tier: RichTextTier;
  /** Extra buttons rendered inside the same scrollable row, before/after the
   * built-in groups — how session notes add a template picker and a share
   * toggle without the generic toolbar knowing what either of those is. */
  leadingItems?: ReactNode;
  trailingItems?: ReactNode;
}) {
  const label = useLabels();
  const full = tier === "full";
  const { ref: scrollRef, canScrollLeft, canScrollRight, scrollBy } = useToolbarScroll();

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
      {/* Outside `.toolbarScroll` on purpose — that container's `overflow-x:
          auto` forces `overflow-y` to compute as non-visible too (a CSS
          quirk: an element can't scroll one axis and stay visible on the
          other), which was silently clipping a leading item's dropdown the
          moment it tried to open below the button. Pinning these outside
          the scroller sidesteps the clipping *and* means they're never the
          thing that scrolls out of view — arguably the right call anyway
          for a share-status indicator. */}
      {leadingItems}
      {leadingItems && <span className={styles.toolbarDivider} aria-hidden="true" />}
      {canScrollLeft && (
        <button
          type="button"
          className={styles.toolbarNav}
          aria-label={label("scrollLeft", "Scroll left")}
          onMouseDown={keepEditorFocus}
          onClick={() => scrollBy(-120)}
        >
          <ChevronLeft size={16} />
        </button>
      )}
      <div className={styles.toolbarScroll} ref={scrollRef}>
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
        {trailingItems}
      </div>
      {canScrollRight && (
        <button
          type="button"
          className={styles.toolbarNav}
          aria-label={label("scrollRight", "Scroll right")}
          onMouseDown={keepEditorFocus}
          onClick={() => scrollBy(120)}
        >
          <ChevronRight size={16} />
        </button>
      )}
    </div>
  );
}
