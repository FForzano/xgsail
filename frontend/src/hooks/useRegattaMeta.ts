import { useQuery } from "@tanstack/react-query";
import { clubsService, clubKeys } from "@/services/clubs";
import { boatsService, boatKeys } from "@/services/boats";
import type { Regatta } from "@/types";

/** The names `RegattaHero` needs but deliberately doesn't fetch itself: the
 * organizing club, the boat class, and how many races the regatta holds.
 *
 * Lives in a hook because both the regatta page and the public join landing
 * need exactly the same three, and because there is no `GET /boat-classes/{id}`
 * — resolving a class id means the catalog, so it reuses the same query key
 * the boat pages already populate rather than fetching a second copy. */
export function useRegattaMeta(regatta?: Regatta | null): {
  clubName: string | null;
  boatClassName: string | null;
  raceCount: number;
} {
  const club = useQuery({
    queryKey: clubKeys.detail(regatta?.club_id ?? "none"),
    queryFn: () => clubsService.get(regatta!.club_id),
    enabled: !!regatta?.club_id,
  });

  const classes = useQuery({
    queryKey: boatKeys.classes(),
    queryFn: () => boatsService.listClasses({ limit: 1000, sort: "name" }),
    enabled: !!regatta?.class_id,
    staleTime: 60 * 60 * 1000,
  });

  const raceCount = (regatta?.race_days ?? []).reduce(
    (n, day) => n + (day.races?.length ?? 0),
    0,
  );

  return {
    clubName: club.data?.name ?? null,
    boatClassName: classes.data?.find((c) => c.id === regatta?.class_id)?.name ?? null,
    raceCount,
  };
}
