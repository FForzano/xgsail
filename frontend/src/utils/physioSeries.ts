import type { HrZone, ScalarSample } from "@/types";
import { lastIndexAtOrBefore } from "./timeSeries";

// Turning the wearable scalar series into something a chart and a cursor
// readout can both use. Two shape mismatches to bridge:
//
//   * samples are stamped with an ISO string, while the playback clock and the
//     recharts x-axis are both epoch ms — so parse once, up front, not per
//     render and certainly not inside a binary search;
//   * active energy is a *cumulative* counter (docs/device-protocol.md §9.2).
//     Plotted raw it is a line that only ever goes up, which says nothing about
//     when the effort happened; `energyRate` turns it into kcal/min.

export interface SeriesPoint {
  ms: number;
  v: number;
}

/** Value key for a sensor type, matching the worker's output column. */
export const VALUE_KEYS = {
  heart_rate: "bpm",
  energy: "kcal",
  hrv: "ms",
  respiration: "brpm",
} as const;

export type PhysioSensor = keyof typeof VALUE_KEYS;

/** ISO-stamped samples -> `{ms, v}` in time order, dropping unusable rows. */
export function prepareSeries(
  points: ScalarSample[] | null | undefined,
  sensor: PhysioSensor,
): SeriesPoint[] {
  const key = VALUE_KEYS[sensor];
  const out: SeriesPoint[] = [];
  for (const p of points ?? []) {
    const ms = Date.parse(p.t);
    const v = p[key];
    if (Number.isNaN(ms) || typeof v !== "number") continue;
    out.push({ ms, v });
  }
  out.sort((a, b) => a.ms - b.ms);
  return out;
}

/** Value at or before `ms`, or null before the series starts. */
export function sampleAt(series: SeriesPoint[], ms: number): number | null {
  const idx = lastIndexAtOrBefore(series, ms, (p) => p.ms);
  return idx < 0 ? null : series[idx].v;
}

/**
 * kcal/min from the cumulative kcal counter.
 *
 * Each output point sits at the end of the interval it describes. Intervals
 * where the counter drops are skipped rather than reported as negative burn:
 * the watch restarting mid-session resets it to zero, which is a gap in
 * knowledge, not the sailor un-burning calories.
 */
export function energyRate(series: SeriesPoint[]): SeriesPoint[] {
  const out: SeriesPoint[] = [];
  for (let i = 1; i < series.length; i++) {
    const prev = series[i - 1];
    const curr = series[i];
    const minutes = (curr.ms - prev.ms) / 60000;
    if (minutes <= 0 || curr.v < prev.v) continue;
    out.push({ ms: curr.ms, v: (curr.v - prev.v) / minutes });
  }
  return out;
}

/**
 * Seconds spent in each heart-rate zone, indexed by `zone`.
 *
 * Each sample is credited with the time until the next one, so an irregular
 * cadence still totals the real elapsed time. Gaps longer than `maxGapMs` are
 * dropped instead of stretched: a watch that lost contact for ten minutes
 * should not report ten minutes in whatever zone it last saw.
 */
export function timeInZones(
  series: SeriesPoint[],
  zones: HrZone[],
  maxGapMs = 60000,
): Map<number, number> {
  const out = new Map<number, number>(zones.map((z) => [z.zone, 0]));
  for (let i = 0; i < series.length - 1; i++) {
    const gap = series[i + 1].ms - series[i].ms;
    if (gap <= 0 || gap > maxGapMs) continue;
    const bpm = series[i].v;
    const zone = zones.find((z) => bpm >= z.min_bpm && bpm <= z.max_bpm);
    // Below zone 1 is rest, above zone 5 can't happen (it ends at the maximum,
    // but a measured max can be exceeded) — both fall outside the bands and are
    // simply not counted towards any of them.
    if (zone) out.set(zone.zone, (out.get(zone.zone) ?? 0) + gap / 1000);
  }
  return out;
}

/** Min/max of a series, padded so a flat line isn't drawn on the axis itself. */
export function seriesDomain(series: SeriesPoint[]): [number, number] {
  if (!series.length) return [0, 1];
  let lo = series[0].v;
  let hi = series[0].v;
  for (const p of series) {
    if (p.v < lo) lo = p.v;
    if (p.v > hi) hi = p.v;
  }
  if (lo === hi) return [lo - 1, hi + 1];
  const pad = (hi - lo) * 0.1;
  return [lo - pad, hi + pad];
}
