import { Suspense, lazy, useId, type CSSProperties, type ReactNode } from "react";
import type { RichTextTier } from "./RichText";
import { mergeTitleBody, splitTitleBody } from "./richTextHtml";
import styles from "./RichText.module.css";

// Tiptap + ProseMirror are ~120KB gzip and most sessions never open an editor,
// so they load only once a field is actually rendered — and an OTA bundle the
// native app downloads whole stays that much smaller.
const RichTextEditor = lazy(() => import("./RichTextEditor"));

const DEFAULT_MIN_HEIGHT: Record<RichTextTier, string> = {
  basic: "14rem",
  full: "22rem",
};

/** Rich-text sibling of `TextAreaField`: same label/id/value/onChange shape, so
 * swapping a form's textarea for one needs no restructuring. */
export function RichTextField({
  label,
  id,
  value,
  onChange,
  tier = "basic",
  mentions = false,
  placeholder,
  minHeight,
  disabled,
  title,
  onTitleChange,
  titlePlaceholder,
  leadingToolbarItems,
  trailingToolbarItems,
  fill,
}: {
  label: string;
  id: string;
  value: string;
  onChange: (html: string) => void;
  tier?: RichTextTier;
  mentions?: boolean;
  placeholder?: string;
  minHeight?: string;
  disabled?: boolean;
  /** Merged title: `title`/`body` stay two genuinely separate fields (own DB
   * column, own form state) as far as the caller is concerned, but on
   * screen there is no separate input for it at all — it's simply the
   * document's first paragraph, scrolling with the rest of the text and
   * drawn larger by a CSS rule keyed on position, not by being some special
   * kind of node. Pass `title`/`onTitleChange` to turn this on; every
   * change re-derives both fields from the one document (see
   * `richTextHtml.ts`'s `mergeTitleBody`/`splitTitleBody`) and calls both
   * back. */
  title?: string;
  onTitleChange?: (value: string) => void;
  titlePlaceholder?: string;
  /** Extra buttons in the toolbar's single scrollable row, before/after the
   * built-in formatting groups — e.g. a template picker or a share toggle
   * that only some call sites need. */
  leadingToolbarItems?: ReactNode;
  trailingToolbarItems?: ReactNode;
  /** Stretches the field to fill its container's remaining height — pair
   * with `Modal`'s `fillBody`, for a modal whose one job is this editor. */
  fill?: boolean;
}) {
  const labelId = useId();
  const hasTitle = onTitleChange !== undefined;
  // `fill` means this field is the modal's one and only job — the modal's
  // own title already names it, so a second visible caption above the
  // editor is redundant and, worse, is vertical space the "fill the whole
  // modal" request explicitly wants back.
  const hideLabel = hasTitle || fill;
  // A contenteditable is not a labelable element, so the association is
  // `aria-labelledby` rather than the `htmlFor` a textarea would use.
  const style = {
    "--rt-min-height": minHeight ?? DEFAULT_MIN_HEIGHT[tier],
  } as CSSProperties;

  const editorValue = hasTitle ? mergeTitleBody(title!, value) : value;
  const handleEditorChange = (html: string) => {
    if (!hasTitle) {
      onChange(html);
      return;
    }
    const { title: nextTitle, body: nextBody } = splitTitleBody(html);
    onTitleChange!(nextTitle);
    onChange(nextBody);
  };

  return (
    // A plain div, not a `<label>`: `<button>` is itself a labelable element,
    // so a `<label>` wrapping the toolbar's buttons implicitly associates
    // with them — clicking anywhere else inside it (the prose text) then
    // makes the browser replay a synthetic click on the first one (Bold),
    // toggling it on every unrelated click. `aria-labelledby` below is the
    // real association, same reason it's used instead of `htmlFor`.
    <div className={`sf-field ${fill ? styles.fieldFill : ""}`}>
      {/* Still in the accessibility tree when hidden visually — the field
          needs *a* name, just not a second visible caption floating above
          what a fill modal's own title (or the merged first line) already
          names. */}
      <span className={`sf-field__label ${hideLabel ? styles.srOnly : ""}`} id={labelId}>
        {label}
      </span>
      <div
        className={`sf-field__input ${styles.editor} ${fill ? styles.editorFill : ""} ${
          disabled ? styles.editorDisabled : ""
        }`}
        style={style}
      >
        <Suspense
          fallback={
            <div className={`${styles.content} ${styles.placeholder}`} aria-hidden="true">
              {hasTitle ? titlePlaceholder : placeholder}
            </div>
          }
        >
          <RichTextEditor
            id={id}
            labelId={labelId}
            value={editorValue}
            onChange={handleEditorChange}
            tier={tier}
            mentions={mentions}
            placeholder={placeholder}
            titlePlaceholder={hasTitle ? titlePlaceholder : undefined}
            hasMergedTitle={hasTitle}
            disabled={disabled}
            leadingToolbarItems={leadingToolbarItems}
            trailingToolbarItems={trailingToolbarItems}
          />
        </Suspense>
      </div>
    </div>
  );
}
