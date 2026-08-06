import { useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { clubsService, clubKeys } from "@/services/clubs";
import { groupsService, groupKeys } from "@/services/groups";
import { RichTextField } from "@/components/ui/RichTextField";
import {
  MentionSuggestionContext,
  type MentionAttrs,
  type MentionSuggestionHandle,
} from "@/components/ui/richTextMentions";
import { userLabel } from "@/utils/format";
import { smartSearch } from "@/utils/smartSearch";
import type { PostOwnerType, UUID } from "@/types";
import styles from "./EntityFeed.module.css";

interface MentionCandidate {
  type: MentionAttrs["entityType"];
  id: UUID;
  label: string;
}

const MAX_RESULTS = 8;

/** Rich-text body for a post, shared between creating one (`PostComposer`) and
 * editing an existing one — factored out so the two don't duplicate the
 * `@mention` candidate source. Formatting itself is `RichTextField`'s job; what
 * this component adds is the list of people/clubs/groups behind `@`, rendered
 * into the floating layer the Tiptap suggestion plugin positions at the caret. */
export function PostBodyField({
  ownerType,
  ownerId,
  value,
  onChange,
  id,
  placeholder,
}: {
  ownerType: PostOwnerType;
  ownerId: UUID;
  value: string;
  onChange: (value: string) => void;
  id: string;
  placeholder: string;
}) {
  const { t } = useTranslation();

  // --- @mentions: candidates are the post's own club/group members (visible
  // to whoever can already post here) plus every club/group name, mirroring
  // the same "search over already-loaded lists" pattern as EntitySearch —
  // there's no dedicated backend search endpoint for this. ---
  const clubs = useQuery({ queryKey: clubKeys.all, queryFn: clubsService.list });
  const groups = useQuery({ queryKey: groupKeys.all, queryFn: () => groupsService.list() });
  const clubMembers = useQuery({
    queryKey: clubKeys.members(ownerId),
    queryFn: () => clubsService.members(ownerId),
    enabled: ownerType === "club",
  });
  const groupDetail = useQuery({
    queryKey: groupKeys.detail(ownerId),
    queryFn: () => groupsService.get(ownerId),
    enabled: ownerType === "group",
  });

  const mentionCandidates = useMemo((): MentionCandidate[] => {
    const members = ownerType === "club" ? clubMembers.data : groupDetail.data?.members;
    return [
      ...(members ?? [])
        .filter((m) => m.user)
        .map((m): MentionCandidate => ({ type: "user", id: m.user_id, label: userLabel(m.user) })),
      ...(clubs.data ?? []).map((c): MentionCandidate => ({ type: "club", id: c.id, label: c.name })),
      ...(groups.data ?? []).map((g): MentionCandidate => ({ type: "group", id: g.id, label: g.name })),
    ];
  }, [ownerType, clubMembers.data, groupDetail.data, clubs.data, groups.data]);

  // `null` while the `@` suggestion is closed. The plugin owns when it opens
  // and what the query is; the search and the list below are ours.
  const [query, setQuery] = useState<string | null>(null);
  const [active, setActive] = useState(0);

  const results = useMemo(
    () => (query === null ? [] : smartSearch(query, mentionCandidates, (c) => [c.label]).slice(0, MAX_RESULTS)),
    [query, mentionCandidates],
  );

  // The suggestion plugin calls in from outside React (a ProseMirror view
  // update), so the keyboard handler reads the current list through refs
  // rather than a stale closure.
  const latest = useRef({ results, active, query });
  latest.current = { results, active, query };
  const selectRef = useRef<((attrs: MentionAttrs) => void) | null>(null);

  const select = (candidate: MentionCandidate) => {
    selectRef.current?.({ entityType: candidate.type, id: candidate.id, label: candidate.label });
  };

  const handleRef = useRef<MentionSuggestionHandle | null>(null);
  if (!handleRef.current) {
    // The plugin appends this element to the document and keeps it anchored to
    // the caret; the list itself is portalled into it, so it stays inside this
    // component's React tree (and its query/i18n context).
    const element = document.createElement("div");
    element.className = styles.mentionLayer;
    handleRef.current = {
      element,
      show: ({ query: next, select: command }) => {
        selectRef.current = command;
        if (latest.current.query !== next) setActive(0);
        setQuery(next);
      },
      hide: () => {
        selectRef.current = null;
        setQuery(null);
      },
      onKeyDown: (event) => {
        const items = latest.current.results;
        if (items.length === 0) return false;
        if (event.key === "ArrowDown") {
          setActive((i) => (i + 1) % items.length);
          return true;
        }
        if (event.key === "ArrowUp") {
          setActive((i) => (i - 1 + items.length) % items.length);
          return true;
        }
        if (event.key === "Enter" || event.key === "Tab") {
          select(items[latest.current.active]);
          return true;
        }
        return false;
      },
    };
  }

  return (
    <MentionSuggestionContext.Provider value={handleRef}>
      <RichTextField
        label={placeholder}
        id={id}
        value={value}
        onChange={onChange}
        tier="basic"
        mentions
        placeholder={placeholder}
        minHeight="8rem"
      />
      {query !== null &&
        results.length > 0 &&
        createPortal(
          <div
            className={styles.formMentions}
            role="listbox"
            aria-label={t("richText.mentionSuggestions", { defaultValue: "Mention suggestions" })}
          >
            {results.map((c, i) => (
              <div
                key={`${c.type}-${c.id}`}
                role="option"
                aria-selected={i === active}
                className={`${styles.formMentionOption} ${i === active ? styles.formMentionOptionActive : ""}`}
                // Pointer, not click: the editor must keep focus and the caret
                // where the `@` query still is, or the insert has no range.
                onPointerDown={(e) => {
                  e.preventDefault();
                  select(c);
                }}
              >
                <span>{c.label}</span>
                <span className={styles.formMentionType}>{t(`gruppi.mentionType.${c.type}`)}</span>
              </div>
            ))}
          </div>,
          handleRef.current.element,
        )}
    </MentionSuggestionContext.Provider>
  );
}
