import { Suspense, lazy, useId, type CSSProperties } from "react";
import type { RichTextTier } from "./RichText";
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
}) {
  const labelId = useId();
  // A contenteditable is not a labelable element, so the association is
  // `aria-labelledby` rather than the `htmlFor` a textarea would use.
  const style = {
    "--rt-min-height": minHeight ?? DEFAULT_MIN_HEIGHT[tier],
  } as CSSProperties;

  return (
    <label className="sf-field">
      <span className="sf-field__label" id={labelId}>
        {label}
      </span>
      <div
        className={`sf-field__input ${styles.editor} ${disabled ? styles.editorDisabled : ""}`}
        style={style}
      >
        <Suspense
          fallback={
            <div className={`${styles.content} ${styles.placeholder}`} aria-hidden="true">
              {placeholder}
            </div>
          }
        >
          <RichTextEditor
            id={id}
            labelId={labelId}
            value={value}
            onChange={onChange}
            tier={tier}
            mentions={mentions}
            placeholder={placeholder}
            disabled={disabled}
          />
        </Suspense>
      </div>
    </label>
  );
}
