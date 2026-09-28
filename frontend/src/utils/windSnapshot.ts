import type { TFunction } from "i18next";
import type { WindSnapshot } from "@/types";

/** True for the fused multi-source `/wind/nearest` shape rather than an
 * older server's pre-fusion single-source reading (see `WindSnapshot`). */
export function isFusedWind(snapshot: WindSnapshot): boolean {
  return snapshot.provider === "fusion";
}

/** Short attribution label for a wind reading: "Combined estimate (N
 * sources)" for the fused shape, the station/model/provider name otherwise —
 * reused everywhere a snapshot's origin is shown (WindCard, nav
 * instruments). */
export function windSourceLabel(snapshot: WindSnapshot, t: TFunction): string {
  if (isFusedWind(snapshot)) {
    return t("wind.fusedSource", { count: snapshot.sources?.length ?? 0 });
  }
  return snapshot.station_name ?? snapshot.model ?? snapshot.provider;
}

/** Minutes since the reading was taken. A fused snapshot's `observed_at` is
 * the instant asked for, not a reading time, so age comes from
 * `latest_observed_at` (the newest underlying observation) instead —
 * falling back to `observed_at` for the older, sourceless shape. */
export function windAgeMinutes(snapshot: WindSnapshot, nowMs: number): number {
  const at = snapshot.latest_observed_at ?? snapshot.observed_at;
  return Math.max(0, Math.round((nowMs - Date.parse(at)) / 60_000));
}

/** Top `n` contributing sources by weight share, for a compact attribution
 * list (WindCard). Empty for the older, sourceless shape — `sources` is
 * already sorted by share descending by the backend. */
export function topWindSources(snapshot: WindSnapshot, n = 3) {
  return (snapshot.sources ?? []).slice(0, n);
}
