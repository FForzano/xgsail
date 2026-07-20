import type { ReactNode } from "react";
import { Link } from "react-router-dom";

/** Post-body-lite syntax: **bold**, *italic*, __underline__, [label](url),
 * and @[label](user|club|group:id) mentions, plus bare "https://…" URLs
 * auto-linked even without the [label](url) form. Deliberately not full
 * Markdown — just enough to cover the formatting the composer toolbar can
 * produce, kept as plain text end to end (no HTML/sanitizer needed) so
 * `body` stays a simple string both in the DB and over the wire. Newline
 * preservation is handled by the `white-space: pre-wrap` on
 * `.sf-feed__post-body`, not here. */
const INLINE_RE =
  /@\[([^\]]+)\]\((user|club|group):([^)]+)\)|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\*\*([^*\n]+)\*\*|__([^_\n]+)__|\*([^*\n]+)\*|(https?:\/\/\S+)/g;

// Trailing punctuation that's almost always sentence structure, not part of
// the URL itself (e.g. "visit https://example.com." or "(see https://x.io)").
const URL_TRAILING_PUNCTUATION_RE = /[),.;:!?\]]+$/;

export function renderPostBody(body: string): ReactNode {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;
  INLINE_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = INLINE_RE.exec(body))) {
    if (m.index > lastIndex) nodes.push(body.slice(lastIndex, m.index));
    const [, mentionLabel, mentionType, mentionId, linkLabel, linkUrl, bold, underline, italic, bareUrl] = m;
    if (mentionLabel !== undefined) {
      if (mentionType === "user") {
        nodes.push(
          <span key={key++} className="sf-mention">
            @{mentionLabel}
          </span>,
        );
      } else {
        const to = mentionType === "club" ? `/gruppi/clubs/${mentionId}` : `/gruppi/${mentionId}`;
        nodes.push(
          <Link key={key++} to={to} className="sf-mention sf-mention--link">
            @{mentionLabel}
          </Link>,
        );
      }
    } else if (linkLabel !== undefined) {
      nodes.push(
        <a key={key++} href={linkUrl} target="_blank" rel="noopener noreferrer">
          {linkLabel}
        </a>,
      );
    } else if (bold !== undefined) {
      nodes.push(<strong key={key++}>{bold}</strong>);
    } else if (underline !== undefined) {
      nodes.push(<u key={key++}>{underline}</u>);
    } else if (italic !== undefined) {
      nodes.push(<em key={key++}>{italic}</em>);
    } else if (bareUrl !== undefined) {
      const trailing = bareUrl.match(URL_TRAILING_PUNCTUATION_RE)?.[0] ?? "";
      const url = trailing ? bareUrl.slice(0, -trailing.length) : bareUrl;
      nodes.push(
        <a key={key++} href={url} target="_blank" rel="noopener noreferrer">
          {url}
        </a>,
      );
      if (trailing) nodes.push(trailing);
    }
    lastIndex = INLINE_RE.lastIndex;
  }
  if (lastIndex < body.length) nodes.push(body.slice(lastIndex));
  return nodes;
}
