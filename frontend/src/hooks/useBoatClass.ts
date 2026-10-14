import { useQuery } from "@tanstack/react-query";
import { boatsService } from "@/services/boats";
import type { BoatClass, UUID } from "@/types";

/** A boat's class record, e.g. for drawing the right silhouette on a map.
 * Reads the class catalogue — one small request shared by every caller and
 * kept for the session, since classes barely change — rather than adding a
 * per-boat endpoint. Null while loading or for a boat with no class. */
export function useBoatClass(boatClassId: UUID | null | undefined): BoatClass | null {
  const classes = useQuery({
    // Under the paged catalogue's "boat-classes" prefix, so an edit that
    // invalidates the catalogue refreshes this too.
    queryKey: ["boat-classes", "catalogue"] as const,
    queryFn: () => boatsService.listClasses({ limit: 1000 }),
    enabled: !!boatClassId,
    staleTime: 60 * 60 * 1000,
  });
  return classes.data?.find((c) => c.id === boatClassId) ?? null;
}
