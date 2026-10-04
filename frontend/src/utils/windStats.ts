import type { TrueWindPoint } from "@/types";

export interface WindSummary {
  meanKts: number;
  peakKts: number;
  /** Null when no source behind the series reported gusts — a station
   * without a gust sensor, or an older analysis predating the field. */
  maxGustKts: number | null;
}

/** Mean/peak wind and strongest gust over a session's true-wind series. The
 * series is sampled per GPS fix, i.e. evenly in time, so a plain mean is the
 * time-weighted one. */
export function windSummary(points: TrueWindPoint[] | null | undefined): WindSummary | null {
  const speeds = (points ?? []).map((p) => p.tws_kts).filter((v): v is number => v != null);
  if (!speeds.length) return null;
  const gusts = (points ?? []).map((p) => p.gust_kts).filter((v): v is number => v != null);
  return {
    meanKts: speeds.reduce((a, b) => a + b, 0) / speeds.length,
    peakKts: Math.max(...speeds),
    maxGustKts: gusts.length ? Math.max(...gusts) : null,
  };
}
