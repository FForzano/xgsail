import { useMemo, useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import type { TFunction } from "i18next";
import { activitiesService, activityKeys } from "@/services/activities";
import { regattasService, raceKeys } from "@/services/races";
import { clubsService, clubKeys } from "@/services/clubs";
import { groupsService, groupKeys } from "@/services/groups";
import { useInfiniteScrollSentinel } from "@/hooks/useInfiniteScrollSentinel";
import { activityDisplayName } from "@/utils/activityName";
import type { EventItem, Ownership } from "@/components/diario/EventRow";

const PAGE_SIZE = 20;

/** Shared data/merge logic behind the two diario tabs: "personal" (my own
 * activities + regattas I've raced in) and "clubs" (activities + regattas of
 * every club/group I belong to). Activities paginate via infinite scroll;
 * regattas are fetched in full up front (same no-pagination assumption
 * `ClubEvents`/the old `RegattasPage` already made — regattas are far lower
 * volume than activities). */
export function useDiaryFeed(scope: "personal" | "clubs", t: TFunction) {
  const [type, setType] = useState("");

  const activities = useInfiniteQuery({
    queryKey: activityKeys.list({ type, scope }),
    queryFn: ({ pageParam }) =>
      activitiesService.list({
        type: type || undefined,
        limit: PAGE_SIZE,
        offset: pageParam,
        ...(scope === "personal" ? { mine: true } : { member_clubs: true }),
      }),
    initialPageParam: 0,
    // The API doesn't return a total count — a page shorter than PAGE_SIZE
    // means we've reached the end.
    getNextPageParam: (lastPage, allPages) =>
      lastPage.length < PAGE_SIZE ? undefined : allPages.length * PAGE_SIZE,
  });

  const regattas = useQuery({
    queryKey: [...raceKeys.regattas, scope],
    queryFn: () =>
      scope === "personal" ? regattasService.list({ mine: true }) : regattasService.list({ memberClubs: true }),
  });

  const clubs = useQuery({ queryKey: clubKeys.all, queryFn: clubsService.list });
  const groups = useQuery({ queryKey: groupKeys.all, queryFn: () => groupsService.list(true) });
  const clubName = (id: string) => clubs.data?.find((c) => c.id === id)?.name;
  const groupName = (id: string) => groups.data?.find((g) => g.id === id)?.name;

  const activityList = useMemo(() => activities.data?.pages.flat() ?? [], [activities.data]);

  const items = useMemo<EventItem[]>(() => {
    const activityItems: EventItem[] = activityList
      // Race-tracking activities (type "race", auto-created off
      // `activities.race_id` the first time a race's sessions/marks are
      // touched, see `backend/routers/races.py::_race_activity`) are
      // internal bookkeeping for that race's GPS data — they're already
      // represented by the race itself under its regatta below (see
      // `RegattaRaceDays`), so listing them again here would just
      // duplicate the same race as its own unrelated card (same filter
      // `ClubEvents.tsx` already applies).
      .filter((a) => a.type !== "race")
      .map((a) => {
        const ownership: Ownership = a.club_id
          ? { kind: "club", name: clubName(a.club_id) }
          : a.group_id
            ? { kind: "group", name: groupName(a.group_id) }
            : { kind: "personal" };
        return {
          kind: "activity",
          id: a.id,
          title: activityDisplayName(a, t),
          date: a.started_at,
          endDate: null,
          activity: a,
          ownership,
        };
      });
    const regattaItems: EventItem[] = (regattas.data ?? []).map((r) => ({
      kind: "regatta",
      id: r.id,
      title: r.name,
      date: r.start_date,
      endDate: r.end_date,
      regatta: r,
      ownership: { kind: "club", name: clubName(r.club_id) },
    }));
    return [...activityItems, ...regattaItems].sort(
      (a, b) => new Date(b.date ?? 0).getTime() - new Date(a.date ?? 0).getTime(),
    );
  }, [activityList, regattas.data, clubs.data, groups.data, t]);

  const sentinelRef = useInfiniteScrollSentinel<HTMLDivElement>(
    () => activities.fetchNextPage(),
    activities.hasNextPage === true && !activities.isFetchingNextPage,
  );

  return {
    type,
    setType,
    items,
    isLoading: activities.isLoading || regattas.isLoading,
    hasNextPage: activities.hasNextPage === true,
    sentinelRef,
  };
}
