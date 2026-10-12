import { useQuery } from "@tanstack/react-query";
import { boatsService } from "@/services/boats";
import type { HullType, UUID } from "@/types";

/** The hull type (monohull / multihull) of a boat class, for drawing the right
 * silhouette on a map. Reads the class catalogue — one small request shared by
 * every caller and kept for the session, since classes barely change — rather
 * than adding a per-boat endpoint for a single enum. Null while loading, for a
 * boat with no class, or a class with no hull type set. */
export function useBoatHullType(boatClassId: UUID | null | undefined): HullType | null {
  const classes = useQuery({
    // Under the paged catalogue's "boat-classes" prefix, so an edit that
    // invalidates the catalogue refreshes this too.
    queryKey: ["boat-classes", "catalogue"] as const,
    queryFn: () => boatsService.listClasses({ limit: 1000 }),
    enabled: !!boatClassId,
    staleTime: 60 * 60 * 1000,
  });
  return classes.data?.find((c) => c.id === boatClassId)?.hull_type ?? null;
}
