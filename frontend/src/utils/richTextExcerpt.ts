const BLOCK_TAG_RE = /<\/(p|h1|h2|h3|li|blockquote|tr|div)>/gi;

/**
 * Plain single-line excerpt of a rich-text (or legacy plain-text) field, for
 * card subtitles where a `<p>`/`<ul>` would break a one-line layout.
 * Uses DOMParser (parses, never executes) rather than a tag-stripping regex,
 * which mishandles entities and self-closing/void tags.
 */
export function richTextExcerpt(html: string | null | undefined, maxChars: number): string {
  if (!html) return "";
  // Insert a space at block boundaries before parsing, so `<p>a</p><p>b</p>`
  // reads as "a b" instead of "ab" once textContent drops the tags.
  const withBoundaries = html.replace(BLOCK_TAG_RE, "$& ");
  const doc = new DOMParser().parseFromString(withBoundaries, "text/html");
  const text = (doc.body.textContent ?? "").replace(/\s+/g, " ").trim();

  if (text.length <= maxChars) return text;

  const cut = text.slice(0, maxChars);
  const lastSpace = cut.lastIndexOf(" ");
  // Only break on a word boundary if it doesn't throw away most of the
  // excerpt (e.g. one long unbroken token) — otherwise a hard cut is closer
  // to the requested length.
  const truncated = lastSpace > maxChars * 0.5 ? cut.slice(0, lastSpace) : cut;
  return `${truncated.trimEnd()}…`;
}
