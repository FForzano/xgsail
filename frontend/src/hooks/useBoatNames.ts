import { useQueries } from "@tanstack/react-query";
import { boatsService, boatKeys } from "@/services/boats";
import type { UUID } from "@/types";

/** Resolve display names for a known, small set of boat IDs (a race's results,
 * a regatta's start list).
 *
 * Per-boat fetches rather than one list call: these views show a few dozen
 * boats out of however many the instance holds, and pulling the whole table
 * just to map IDs to names is what made the results editor unusable. Each boat
 * is cached under its own key, so overlapping views share the fetches. */
export function useBoatNames(boatIds: UUID[]): (id: UUID) => string {
  const unique = Array.from(new Set(boatIds));
  const results = useQueries({
    queries: unique.map((id) => ({
      queryKey: boatKeys.detail(id),
      queryFn: () => boatsService.get(id),
      staleTime: 5 * 60 * 1000,
    })),
  });

  const names = new Map<UUID, string>();
  unique.forEach((id, i) => {
    const boat = results[i]?.data;
    if (boat) names.set(id, boat.sail_number ? `${boat.name} — ${boat.sail_number}` : boat.name);
  });

  // Falls back to a short ID while the fetch is in flight, so rows never
  // collapse to blank.
  return (id: UUID) => names.get(id) ?? id.slice(0, 8);
}
