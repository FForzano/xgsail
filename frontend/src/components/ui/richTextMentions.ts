import { createContext } from "react";

/** The entity kinds a post body can mention. Mirrors the `type:id` half of the
 * `data-mention` attribute the backend sanitizer allows. */
export type MentionEntityType = "user" | "club" | "group";

/** A mention node's attributes — also the payload the suggestion list hands
 * back when the user picks a candidate. */
export interface MentionAttrs {
  entityType: MentionEntityType;
  id: string;
  label: string;
}

/** Bridge between Tiptap's imperative `suggestion` plugin (which lives in the
 * lazily-loaded editor chunk) and the React list that renders the candidates.
 * The editor calls into it; the form owning the candidate source implements it.
 *
 * Kept in this tiptap-free module on purpose: the form providing the handle is
 * part of the eager bundle, and importing it from `richTextSchema.ts` would
 * drag ProseMirror out of the lazy chunk.
 */
export interface MentionSuggestionHandle {
  /** The list's DOM home — the plugin mounts and positions this element. */
  element: HTMLElement;
  /** Called on open and on every query change. */
  show(state: { query: string; select: (attrs: MentionAttrs) => void }): void;
  hide(): void;
  /** `true` when the list consumed the key (arrows/enter/tab). */
  onKeyDown(event: KeyboardEvent): boolean;
}

export interface MentionSuggestionRef {
  readonly current: MentionSuggestionHandle | null;
}

/** `null` (the default) means no candidate source is in scope, so `@` stays
 * inert even where the schema allows mention nodes. */
export const MentionSuggestionContext = createContext<MentionSuggestionRef | null>(null);
