/** Pure HTML-string helpers for the rich-text editor, deliberately free of
 * any `@tiptap/*` import: `RichTextField.tsx` (part of the *eager* bundle —
 * every page with a description field renders it outside any `<Suspense>`)
 * needs the title-merge helpers below, and `RichTextEditor.tsx` (the
 * lazy-loaded chunk) needs `toEditorHtml`. Importing either straight from
 * the other's module would drag ProseMirror into whichever one is eager. */

const BLOCK_TAG_RE = /^\s*<(p|h1|h2|h3|ul|ol|blockquote|table)[\s/>]/i;

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Mirrors `backend/richtext.py`'s `_plain_text_to_html`: rows written before
 * the rich-text migration hold bare text with newlines, and handing that to
 * `setContent` as a string would collapse every line break. */
export function toEditorHtml(value: string): string {
  if (!value.trim()) return "";
  if (BLOCK_TAG_RE.test(value)) return value;
  return escapeHtml(value.replace(/\r\n?/g, "\n"))
    .split(/\n\s*\n/)
    .filter((block) => block.trim())
    .map((block) => `<p>${block.replace(/^\n+|\n+$/g, "").replace(/\n/g, "<br>")}</p>`)
    .join("");
}

/** Combines a separate title (plain text) and body (HTML or legacy plain
 * text) into one document for the editor — the title becomes the document's
 * first paragraph, with no tag of its own to mark it as special. What makes
 * it "the title" is purely that it's first; a CSS rule (`.hasMergedTitle`,
 * see RichText.module.css) is what draws it larger, so the underlying node
 * needs nothing more than the plain text every other paragraph has. */
export function mergeTitleBody(title: string, body: string): string {
  return `<p>${escapeHtml(title)}</p>${toEditorHtml(body)}`;
}

/** The inverse of `mergeTitleBody`, run on every edit: the editor only ever
 * hands back one HTML string, so the first top-level block is peeled off as
 * `title` (its plain text — any formatting there doesn't survive, since the
 * backend's `title` column is plain text) and everything after becomes
 * `body`. Uses `DOMParser` rather than a regex because `body` may contain
 * arbitrarily nested markup (tables, lists) that a regex can't safely peel
 * a first sibling off of; `DOMParser` never executes the input (no scripts
 * run, no resources load), so this is safe to run on arbitrary editor output. */
export function splitTitleBody(html: string): { title: string; body: string } {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const first = doc.body.firstElementChild;
  const title = first?.textContent?.trim() ?? "";
  first?.remove();
  return { title, body: doc.body.innerHTML };
}
