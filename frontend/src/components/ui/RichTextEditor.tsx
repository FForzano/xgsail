import { useContext, useEffect, useMemo, useRef, type ReactNode } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import { RichTextToolbar } from "./RichTextToolbar";
import { buildRichTextExtensions } from "./richTextSchema";
import { MentionSuggestionContext } from "./richTextMentions";
import { toEditorHtml } from "./richTextHtml";
import type { RichTextTier } from "./RichText";
import styles from "./RichText.module.css";

export interface RichTextEditorProps {
  id: string;
  labelId: string;
  value: string;
  onChange: (html: string) => void;
  tier: RichTextTier;
  mentions: boolean;
  placeholder?: string;
  /** Ghost text for the document's first node specifically — see
   * `RichTextField`'s merged-title mode, which is the only caller that sets
   * this (a plain `placeholder` would otherwise apply to every empty node). */
  titlePlaceholder?: string;
  /** Styles the first top-level node as a title (see RichText.module.css) —
   * on for `RichTextField`'s merged-title mode, off otherwise. */
  hasMergedTitle?: boolean;
  disabled?: boolean;
  leadingToolbarItems?: ReactNode;
  trailingToolbarItems?: ReactNode;
}

export default function RichTextEditor({
  id,
  labelId,
  value,
  onChange,
  tier,
  mentions,
  placeholder,
  titlePlaceholder,
  hasMergedTitle,
  disabled,
  leadingToolbarItems,
  trailingToolbarItems,
}: RichTextEditorProps) {
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  // The HTML the editor itself last produced. Feeding `value` back in on every
  // keystroke would rebuild the document and drop the caret, so an incoming
  // `value` is only applied when it differs from this — i.e. when the *parent*
  // changed it (a form reset after save, a loaded record), not when it is just
  // echoing our own last emission back.
  const lastEmitted = useRef(value);

  // Supplied by whichever form owns the mention candidates (the post composer);
  // absent everywhere else, which leaves `@` inert.
  const mentionSuggestion = useContext(MentionSuggestionContext);

  const extensions = useMemo(
    () => buildRichTextExtensions({ tier, mentions, mentionSuggestion, placeholder, titlePlaceholder }),
    [tier, mentions, mentionSuggestion, placeholder, titlePlaceholder],
  );

  const editor = useEditor(
    {
      extensions,
      content: toEditorHtml(value),
      editable: !disabled,
      editorProps: {
        attributes: {
          id,
          role: "textbox",
          "aria-multiline": "true",
          "aria-labelledby": labelId,
        },
      },
      onUpdate: ({ editor: instance }) => {
        const html = instance.isEmpty ? "" : instance.getHTML();
        lastEmitted.current = html;
        onChangeRef.current(html);
      },
    },
    [extensions],
  );

  useEffect(() => {
    if (!editor || value === lastEmitted.current) return;
    const next = toEditorHtml(value);
    lastEmitted.current = value;
    if (next === (editor.isEmpty ? "" : editor.getHTML())) return;
    editor.commands.setContent(next, { emitUpdate: false });
  }, [editor, value]);

  useEffect(() => {
    editor?.setEditable(!disabled);
  }, [editor, disabled]);

  if (!editor) return null;

  return (
    <>
      {!disabled && (
        <RichTextToolbar
          editor={editor}
          tier={tier}
          leadingItems={leadingToolbarItems}
          trailingItems={trailingToolbarItems}
        />
      )}
      <EditorContent
        className={`${styles.content} ${styles.prose} ${hasMergedTitle ? styles.hasMergedTitle : ""}`}
        editor={editor}
      />
    </>
  );
}
