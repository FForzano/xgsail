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

export interface WindSeriesRow {
  ms: number;
  mean: number;
  /** `[mean, gust]` — drawn as the band between the two; absent where no
   * gust was reported. */
  gustBand?: [number, number];
  gust?: number;
}

/** The series downsampled to at most `buckets` evenly spaced time slots —
 * a true-wind row exists per GPS fix, i.e. thousands, far more than a
 * chart a few hundred pixels wide can show. A slot keeps the mean of its
 * mean wind and the max of its gusts, so a gust never disappears into an
 * average. */
export function windSeries(points: TrueWindPoint[] | null | undefined, buckets = 160): WindSeriesRow[] {
  const pts = (points ?? []).filter((p) => p.tws_kts != null);
  if (!pts.length) return [];
  const t0 = pts[0].timestamp;
  const span = Math.max(pts[pts.length - 1].timestamp - t0, 1);
  const slots: { t: number; sum: number; n: number; gust: number | null }[] = [];
  for (const p of pts) {
    const i = Math.min(buckets - 1, Math.floor(((p.timestamp - t0) / span) * buckets));
    const s = (slots[i] ??= { t: 0, sum: 0, n: 0, gust: null });
    s.t += p.timestamp;
    s.sum += p.tws_kts as number;
    s.n += 1;
    if (p.gust_kts != null) s.gust = Math.max(s.gust ?? 0, p.gust_kts);
  }
  return slots
    .filter(Boolean)
    .map((s) => {
      const mean = s.sum / s.n;
      const row: WindSeriesRow = { ms: (s.t / s.n) * 1000, mean };
      if (s.gust != null) {
        row.gust = Math.max(s.gust, mean);
        row.gustBand = [mean, row.gust];
      }
      return row;
    });
}
