import { useContext, useEffect, useMemo, useRef } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import { RichTextToolbar } from "./RichTextToolbar";
import { buildRichTextExtensions } from "./richTextSchema";
import { MentionSuggestionContext } from "./richTextMentions";
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
  disabled?: boolean;
}

const BLOCK_TAG_RE = /^\s*<(p|h1|h2|h3|ul|ol|blockquote|table)[\s/>]/i;

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Mirrors `backend/richtext.py`'s `_plain_text_to_html`: rows written before
 * the rich-text migration hold bare text with newlines, and handing that to
 * `setContent` as a string would collapse every line break. */
function toEditorHtml(value: string): string {
  if (!value.trim()) return "";
  if (BLOCK_TAG_RE.test(value)) return value;
  return escapeHtml(value.replace(/\r\n?/g, "\n"))
    .split(/\n\s*\n/)
    .filter((block) => block.trim())
    .map((block) => `<p>${block.replace(/^\n+|\n+$/g, "").replace(/\n/g, "<br>")}</p>`)
    .join("");
}

export default function RichTextEditor({
  id,
  labelId,
  value,
  onChange,
  tier,
  mentions,
  placeholder,
  disabled,
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
    () => buildRichTextExtensions({ tier, mentions, mentionSuggestion, placeholder }),
    [tier, mentions, mentionSuggestion, placeholder],
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
      {!disabled && <RichTextToolbar editor={editor} tier={tier} />}
      <EditorContent className={`${styles.content} ${styles.prose}`} editor={editor} />
    </>
  );
}
