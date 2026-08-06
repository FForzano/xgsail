import { useMemo, type MouseEvent } from "react";
import DOMPurify from "dompurify";
import { useNavigate } from "react-router-dom";
import styles from "./RichText.module.css";

export type RichTextTier = "basic" | "full";

const TAG_TIERS: Record<RichTextTier, string[]> = {
  basic: ["p", "br", "strong", "em", "u", "s", "a"],
  full: [
    "p",
    "br",
    "strong",
    "em",
    "u",
    "s",
    "a",
    "h1",
    "h2",
    "h3",
    "ul",
    "ol",
    "li",
    "blockquote",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
  ],
};

const BLOCK_TAG_RE = /^\s*<(p|h1|h2|h3|ul|ol|blockquote|table)[\s/>]/i;
// `<p></p>`, `<p><br></p>`, or a handful of those with only whitespace in between —
// what a Tiptap editor emits for "no content".
const EMPTY_HTML_RE = /^(\s*<p>(\s|<br\s*\/?>)*<\/p>\s*)+$/i;

function isBlank(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return true;
  return EMPTY_HTML_RE.test(trimmed);
}

function buildSanitizeConfig(tier: RichTextTier, mentions: boolean) {
  const tags = [...TAG_TIERS[tier]];
  const attrs = ["href", "title", "colspan", "rowspan"];
  if (mentions) {
    tags.push("span");
    attrs.push("data-mention");
  }
  return {
    ALLOWED_TAGS: tags,
    ALLOWED_ATTR: attrs,
    ALLOWED_URI_REGEXP: /^(?:https?:|mailto:|\/(?!\/))/i,
  };
}

function isSameOriginHref(href: string): boolean {
  if (href.startsWith("/") && !href.startsWith("//")) return true;
  try {
    return new URL(href, window.location.href).origin === window.location.origin;
  } catch {
    return false;
  }
}

export function RichText(props: {
  html: string | null | undefined;
  tier?: RichTextTier;
  mentions?: boolean;
  className?: string;
}): JSX.Element | null {
  const { html, tier = "basic", mentions = false, className } = props;
  const navigate = useNavigate();

  const sanitized = useMemo(() => {
    if (!html || isBlank(html)) return null;
    if (!BLOCK_TAG_RE.test(html)) return null; // legacy plain-text path, handled below
    const config = buildSanitizeConfig(tier, mentions);
    // DOMPurify hooks are global (module-level), so add/remove around this single
    // call rather than a persistent instance-level hook, to avoid leaking the
    // hook into unrelated sanitize() calls elsewhere in the app.
    DOMPurify.addHook("afterSanitizeAttributes", (node) => {
      if (node.tagName === "A" && node.hasAttribute("href")) {
        const href = node.getAttribute("href") ?? "";
        if (!isSameOriginHref(href)) {
          node.setAttribute("target", "_blank");
          node.setAttribute("rel", "noopener noreferrer nofollow");
        }
      }
    });
    try {
      return DOMPurify.sanitize(html, config);
    } finally {
      DOMPurify.removeHook("afterSanitizeAttributes");
    }
  }, [html, tier, mentions]);

  const plainText = useMemo(() => {
    if (sanitized !== null) return null;
    if (!html || isBlank(html)) return null;
    return html;
  }, [html, sanitized]);

  if (sanitized === null && plainText === null) return null;

  const containerClassName = `${styles.prose} ${className ?? ""}`.trim();

  if (plainText !== null) {
    return (
      <div className={containerClassName}>
        <span className={styles.plain}>{plainText}</span>
      </div>
    );
  }

  const handleClick = (event: MouseEvent<HTMLDivElement>) => {
    if (event.defaultPrevented) return;
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    const target = event.target as HTMLElement;
    const anchor = target.closest("a");
    if (!anchor || !event.currentTarget.contains(anchor)) return;
    const href = anchor.getAttribute("href");
    if (!href) return;
    if (anchor.target === "_blank") return;
    if (!isSameOriginHref(href)) return;
    event.preventDefault();
    const url = new URL(href, window.location.href);
    navigate(`${url.pathname}${url.search}${url.hash}`);
  };

  return (
    <div
      className={containerClassName}
      onClick={handleClick}
      // eslint-disable-next-line react/no-danger -- sole sanctioned use, see RichText's role as the app's only rich-text renderer
      dangerouslySetInnerHTML={{ __html: sanitized as string }}
    />
  );
}
