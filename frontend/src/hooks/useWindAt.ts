import { useQuery } from "@tanstack/react-query";
import { windService, windKeys } from "@/services/wind";
import type { WindSnapshot } from "@/types";

/** Quick live wind value for a coordinate/time — WindCard/map display only,
 * not the rigorous per-session estimate (see MapView's `sessionWind` prop
 * for that, when a session has one). Nothing is persisted; see
 * backend/services/wind_lookup.live_snapshot. */
export function useWindAt(
  lat: number | undefined,
  lng: number | undefined,
  at?: string | null
): { data: WindSnapshot | null; isLoading: boolean } {
  const hasCoords = lat != null && lng != null;

  const snapshot = useQuery({
    queryKey: hasCoords ? windKeys.nearest(lat, lng, at ?? undefined) : ["wind", "none"],
    queryFn: () => windService.nearest(lat!, lng!, at ?? undefined),
    enabled: hasCoords,
    staleTime: 15 * 60 * 1000,
    retry: false, // 404 = nothing available near this point, not worth retrying
  });

  return { data: snapshot.data ?? null, isLoading: hasCoords && snapshot.isLoading };
}
