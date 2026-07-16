import type { ActivitySessionData, GpsPoint, VmgPoint } from "@/types";

// A replay track: parsed points (ms epoch) + a stable display color.
export interface TrackPoint {
  ms: number;
  lat: number;
  lon: number;
  sog: number;
}
export interface Track {
  id: string;
  name: string;
  color: string;
  pts: TrackPoint[];
  /** The boat's own photo (first of `Boat.photos`), shown in the track-click
   * popup next to its name when present. */
  boatImageUrl?: string | null;
  /** This track's own VMG series — lets the click popup fill in VMG/course
   * even on a multi-track map (e.g. the activity map), where each session
   * has a different series and the map-wide `vmg` prop doesn't apply. Falls
   * back to the `vmg` prop when absent (the single-track session map case). */
  vmg?: VmgPoint[] | null;
}

// Distinct, colorblind-ish palette assigned by track order.
const PALETTE = ["#2f9be0", "#e0654f", "#3fbf7f", "#e0b24a", "#9b6fe0", "#4fd0e0"];

// How many neighboring fixes average into each rendered map point — kept
// small on purpose so tack/gybe corners stay sharp; only for the drawn line,
// never for speed/position data (playback marker, chart, indicators all
// still read the raw fixes).
const MAP_SMOOTH_WINDOW = 3;

/** Centered moving average of a track's lat/lon, for a slightly cleaner
 * drawn line without touching the underlying GPS fixes (sog/ms/position used
 * elsewhere stay exact). Edge points are clamped, not padded, so the ends
 * don't drift. */
export function smoothTrackLine(pts: TrackPoint[], window = MAP_SMOOTH_WINDOW): Array<[number, number]> {
  if (pts.length < window) return pts.map((p) => [p.lat, p.lon]);
  const half = Math.floor(window / 2);
  return pts.map((_, i) => {
    let sumLat = 0;
    let sumLon = 0;
    let n = 0;
    for (let k = -half; k <= half; k++) {
      const idx = Math.min(pts.length - 1, Math.max(0, i + k));
      sumLat += pts[idx].lat;
      sumLon += pts[idx].lon;
      n++;
    }
    return [sumLat / n, sumLon / n];
  });
}

// Extra points drawn per original interval so the line reads as a curve
// instead of a chain of straight chords — kept modest since it multiplies
// the number of drawn segments per interval.
const CURVE_SUBDIVISIONS = 4;

/** Catmull-Rom interpolation between `p1` and `p2`, using `p0`/`p3` as the
 * neighboring control points for the tangent — the standard way to turn a
 * polyline's straight joints into a smooth curve through the same points
 * (no data changes, purely how the segment between two points is drawn).
 * Returns `subdivisions + 1` points from `p1` through `p2` inclusive. */
export function catmullRomInterval(
  p0: [number, number],
  p1: [number, number],
  p2: [number, number],
  p3: [number, number],
  subdivisions = CURVE_SUBDIVISIONS,
): Array<[number, number]> {
  const out: Array<[number, number]> = [p1];
  for (let s = 1; s <= subdivisions; s++) {
    const t = s / subdivisions;
    const t2 = t * t;
    const t3 = t2 * t;
    const lat =
      0.5 *
      (2 * p1[0] +
        (p2[0] - p0[0]) * t +
        (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
        (3 * p1[0] - p0[0] - 3 * p2[0] + p3[0]) * t3);
    const lon =
      0.5 *
      (2 * p1[1] +
        (p2[1] - p0[1]) * t +
        (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
        (3 * p1[1] - p0[1] - 3 * p2[1] + p3[1]) * t3);
    out.push([lat, lon]);
  }
  return out;
}

export function trackColor(i: number): string {
  return PALETTE[i % PALETTE.length];
}

// Sequential blue→cyan→green→yellow→red scale, used to color a track by
// speed (slow = blue, fast = red) instead of the flat per-track PALETTE color.
const SPEED_SCALE: Array<[number, [number, number, number]]> = [
  [0.0, [47, 107, 224]],
  [0.35, [47, 191, 224]],
  [0.6, [63, 191, 127]],
  [0.8, [224, 178, 74]],
  [1.0, [224, 79, 79]],
];

/** Maps `sog` to a color along `SPEED_SCALE`, normalized against [min, max]
 * (typically a single track's own speed range, so its full gradient is used
 * regardless of how fast the boat actually went). */
export function speedColor(sog: number, min: number, max: number): string {
  const t = max > min ? Math.min(1, Math.max(0, (sog - min) / (max - min))) : 0;
  for (let i = 1; i < SPEED_SCALE.length; i++) {
    const [t0, c0] = SPEED_SCALE[i - 1];
    const [t1, c1] = SPEED_SCALE[i];
    if (t <= t1) {
      const f = (t - t0) / (t1 - t0 || 1);
      const r = Math.round(c0[0] + (c1[0] - c0[0]) * f);
      const g = Math.round(c0[1] + (c1[1] - c0[1]) * f);
      const b = Math.round(c0[2] + (c1[2] - c0[2]) * f);
      return `rgb(${r},${g},${b})`;
    }
  }
  const last = SPEED_SCALE[SPEED_SCALE.length - 1][1];
  return `rgb(${last[0]},${last[1]},${last[2]})`;
}

/** [min, max] `sog` across a track's points (both 0 if empty). */
export function speedRange(track: Track): [number, number] {
  let min = Infinity;
  let max = -Infinity;
  for (const p of track.pts) {
    if (p.sog < min) min = p.sog;
    if (p.sog > max) max = p.sog;
  }
  return Number.isFinite(min) ? [min, max] : [0, 0];
}

/** One track from a processed GPS stream (canonical point shape
 * `{t, lat, lon, speed_kn}` — worker output / GPX parse). */
export function buildTrack(
  id: string,
  name: string,
  points: GpsPoint[],
  color: string,
  extra?: { boatImageUrl?: string | null; vmg?: VmgPoint[] | null },
): Track {
  const pts: TrackPoint[] = points
    .filter((p) => p.lat != null && p.lon != null)
    .map((p) => ({
      ms: Date.parse(p.t),
      lat: p.lat,
      lon: p.lon,
      sog: p.speed_kn ?? 0,
    }))
    .sort((a, b) => a.ms - b.ms);
  return { id, name, color, pts, ...extra };
}

/** Tracks from `GET /races/{id}/data` or `GET /activities/{id}/data` —
 * sessions keyed by id, boat embedded. */
export function buildTracks(data: { sessions: ActivitySessionData }): Track[] {
  const tracks: Track[] = [];
  let i = 0;
  for (const [sessionId, entry] of Object.entries(data.sessions ?? {})) {
    const gps = entry.sensors?.gps;
    if (!gps?.length) {
      i++;
      continue;
    }
    tracks.push(buildTrack(sessionId, entry.boat?.name ?? sessionId.slice(0, 8), gps, trackColor(i)));
    i++;
  }
  return tracks.filter((tr) => tr.pts.length > 0);
}

// Nearest point at or before `ms` (no interpolation — marker sits on real fix).
export function pointAt(track: Track, ms: number): TrackPoint | null {
  const i = indexAt(track, ms);
  if (i < 0) return track.pts[0] ?? null;
  return track.pts[i];
}

// Index of the last point at or before `ms` (−1 if before the track starts).
export function indexAt(track: Track, ms: number): number {
  const { pts } = track;
  if (!pts.length || ms < pts[0].ms) return -1;
  let lo = 0;
  let hi = pts.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (pts[mid].ms <= ms) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

// Nearest VMG sample at-or-before `ms` — `vmg_series` is its own time axis
// (epoch seconds, not necessarily the same cadence as GPS fixes), so this
// mirrors `indexAt`'s binary search rather than joining by index.
export function vmgAt(vmg: VmgPoint[] | null | undefined, ms: number): VmgPoint | null {
  if (!vmg?.length || ms < vmg[0].timestamp * 1000) return null;
  let lo = 0;
  let hi = vmg.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (vmg[mid].timestamp * 1000 <= ms) lo = mid;
    else hi = mid - 1;
  }
  return vmg[lo];
}

// Earth radius in meters, for the haversine distance used by the cumulative
// distance helper below.
const EARTH_R_M = 6371000;

function haversineM(a: TrackPoint, b: TrackPoint): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lon - a.lon);
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_R_M * Math.asin(Math.min(1, Math.sqrt(s)));
}

/** Cumulative distance (meters) from the track's start up to and including
 * each point — index-aligned with `track.pts`, for live "distance so far"
 * readouts during playback (paired with `indexAt`). */
export function buildCumulativeDistances(track: Track): number[] {
  const out: number[] = new Array(track.pts.length);
  let total = 0;
  for (let i = 0; i < track.pts.length; i++) {
    if (i > 0) total += haversineM(track.pts[i - 1], track.pts[i]);
    out[i] = total;
  }
  return out;
}

/** Median gap (ms) between consecutive fixes — used to size a sensible
 * step-forward/back jump for the playback transport controls. */
export function medianIntervalMs(track: Track): number {
  const { pts } = track;
  if (pts.length < 2) return 5000;
  const gaps = pts.slice(1).map((p, i) => p.ms - pts[i].ms).sort((a, b) => a - b);
  return gaps[Math.floor(gaps.length / 2)] || 5000;
}

export function timeBounds(tracks: Track[]): [number, number] {
  let min = Infinity;
  let max = -Infinity;
  for (const tr of tracks) {
    if (!tr.pts.length) continue;
    min = Math.min(min, tr.pts[0].ms);
    max = Math.max(max, tr.pts[tr.pts.length - 1].ms);
  }
  return Number.isFinite(min) ? [min, max] : [0, 0];
}
