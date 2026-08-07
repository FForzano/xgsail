import StarterKit from "@tiptap/starter-kit";
import { TableKit } from "@tiptap/extension-table/kit";
import { Mention } from "@tiptap/extension-mention";
import { Placeholder } from "@tiptap/extensions";
import type { AnyExtension } from "@tiptap/core";
import type { RichTextTier } from "./RichText";
import type { MentionAttrs, MentionSuggestionRef } from "./richTextMentions";

/** Single source of truth for what the editor is allowed to produce.
 *
 * Must stay in lockstep with `backend/richtext.py`'s `BASIC_TAGS`/`FULL_TAGS`
 * — a tag this schema can emit but the server-side sanitizer drops is content
 * silently eaten on save, and a tag the sanitizer allows but no extension
 * produces is a feature the user can never reach.
 *
 *   basic: p br strong em u s a
 *   full:  basic + h1 h2 h3 ul ol li blockquote table thead tbody tr th td
 *
 * Attributes the server keeps are `a[href|title]` and `th|td[colspan|rowspan]`
 * only — no class/style/id — which is why nothing here configures
 * `HTMLAttributes`. URL schemes: http, https, mailto.
 */
export interface RichTextSchemaOptions {
  tier: RichTextTier;
  /** Adds the mention node (see the seam below) — its `@` autocomplete only
   * comes alive when a `mentionSuggestion` handle is also supplied. */
  mentions?: boolean;
  mentionSuggestion?: MentionSuggestionRef | null;
}

export const LINK_PROTOCOLS = ["http", "https", "mailto"] as const;

const ALLOWED_LINK_SCHEMES = new Set(["http:", "https:", "mailto:"]);

/** Coerce user input into a link the server-side sanitizer will keep, or
 * `null` if it can't be one. A bare `example.com` gets `https://`. */
export function normalizeLinkHref(raw: string): string | null {
  const value = raw.trim();
  if (!value) return null;
  const candidate = /^[a-z][a-z0-9+.-]*:/i.test(value) ? value : `https://${value}`;
  try {
    const url = new URL(candidate);
    return ALLOWED_LINK_SCHEMES.has(url.protocol) ? url.toString() : null;
  } catch {
    return null;
  }
}

const MENTION_ENTITY_TYPES = new Set(["user", "club", "group"]);

/** Where a mention points, or `null` for a user — users are deliberately not
 * links (there is no public profile page to send a reader to). */
function mentionHref(attrs: MentionAttrs): string | null {
  if (attrs.entityType === "club") return `/gruppi/clubs/${attrs.id}`;
  if (attrs.entityType === "group") return `/gruppi/${attrs.id}`;
  return null;
}

function parseMentionAttrs(element: HTMLElement): MentionAttrs | false {
  const raw = element.getAttribute("data-mention") ?? "";
  const separator = raw.indexOf(":");
  const entityType = raw.slice(0, separator);
  const id = raw.slice(separator + 1);
  if (!MENTION_ENTITY_TYPES.has(entityType) || !id) return false;
  const text = element.textContent ?? "";
  return {
    entityType: entityType as MentionAttrs["entityType"],
    id,
    label: text.startsWith("@") ? text.slice(1) : text,
  };
}

/** One node type, two HTML shapes — `a[href][data-mention]` for a club/group,
 * `span[data-mention]` for a user — chosen by the `entityType` attribute. The
 * shapes are the ones `backend/alembic/versions/0048_richtext_prose.py` wrote
 * and `backend/richtext.py` sanitizes, so `parse → serialize` on a migrated
 * post is byte-identical; the stock `span[data-type="mention"][data-id]` would
 * be stripped on save instead. */
const MentionEntity = Mention.extend({
  addAttributes() {
    return {
      entityType: { default: null },
      id: { default: null },
      label: { default: null },
    };
  },

  parseHTML() {
    return [
      // Above the Link mark's own `a[href]` rule (priority 50), which would
      // otherwise swallow a mention anchor into an ordinary link.
      { tag: "a[data-mention]", priority: 60, getAttrs: parseMentionAttrs },
      { tag: "span[data-mention]", getAttrs: parseMentionAttrs },
    ];
  },

  renderHTML({ node }) {
    const attrs = node.attrs as MentionAttrs;
    const href = mentionHref(attrs);
    const dataMention = `${attrs.entityType}:${attrs.id}`;
    const text = `@${attrs.label}`;
    return href
      ? ["a", { href, "data-mention": dataMention }, text]
      : ["span", { "data-mention": dataMention }, text];
  },
});

function mentionExtension(handleRef: MentionSuggestionRef | null | undefined): AnyExtension {
  return MentionEntity.configure({
    // A mention is one unit: backspace removes the whole node, trigger char
    // included, rather than leaving a stray "@" behind.
    deleteTriggerWithBackspace: true,
    suggestion: {
      char: "@",
      // Searching and rendering belong to the React list behind `handleRef`;
      // this only forwards the plugin's imperative lifecycle to it.
      render: () => {
        let unmount: (() => void) | null = null;
        return {
          onStart: (props) => {
            const handle = handleRef?.current;
            if (!handle) return;
            unmount = props.mount(handle.element);
            handle.show({ query: props.query, select: props.command });
          },
          onUpdate: (props) => {
            handleRef?.current?.show({ query: props.query, select: props.command });
          },
          onKeyDown: ({ event }) => handleRef?.current?.onKeyDown(event) ?? false,
          onExit: () => {
            unmount?.();
            unmount = null;
            handleRef?.current?.hide();
          },
        };
      },
    },
  });
}

export function buildRichTextExtensions(
  options: RichTextSchemaOptions & { placeholder?: string; titlePlaceholder?: string },
): AnyExtension[] {
  const full = options.tier === "full";
  // A merged title+body document (see RichTextField) needs different ghost
  // text on its first node than the rest — Tiptap's Placeholder takes a
  // function precisely for this, keyed on node position rather than a node
  // *type*, since the first node is a plain paragraph like any other, just
  // first.
  const placeholderText = options.titlePlaceholder
    ? ({ pos }: { pos: number }) => (pos === 0 ? options.titlePlaceholder! : (options.placeholder ?? ""))
    : (options.placeholder ?? "");

  const extensions: AnyExtension[] = [
    StarterKit.configure({
      // Outside both allow-lists — `pre`/`code`/`hr`/`img` would be stripped.
      code: false,
      codeBlock: false,
      horizontalRule: false,
      // Tier-gated blocks.
      heading: full ? { levels: [1, 2, 3] } : false,
      bulletList: full ? {} : false,
      orderedList: full ? {} : false,
      listItem: full ? {} : false,
      listKeymap: full ? {} : false,
      blockquote: full ? {} : false,
      // Underline and Link ship inside StarterKit as of Tiptap 3.
      link: {
        protocols: [...LINK_PROTOCOLS],
        defaultProtocol: "https",
        openOnClick: false,
        isAllowedUri: (uri) => normalizeLinkHref(uri) !== null,
      },
    }),
    Placeholder.configure({ placeholder: placeholderText }),
  ];

  if (full) {
    extensions.push(
      TableKit.configure({
        // Column widths ride on `colwidth`/`style`, neither of which survives
        // `backend/richtext.py`, so a resize handle would promise a layout
        // that vanishes on save — and a 5px drag target is unusable on touch.
        table: { resizable: false },
      }),
    );
  }

  // The node goes in whenever mentions are allowed — even with no suggestion
  // handle in scope, or loading an existing post would parse its mentions as
  // plain links/text and lose them on the next save.
  if (options.mentions) {
    extensions.push(mentionExtension(options.mentionSuggestion));
  }

  return extensions;
}
