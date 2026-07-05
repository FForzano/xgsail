import type { GpsPoint, RaceData } from "@/types";

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
}

// Distinct, colorblind-ish palette assigned by track order.
const PALETTE = ["#2f9be0", "#e0654f", "#3fbf7f", "#e0b24a", "#9b6fe0", "#4fd0e0"];

export function trackColor(i: number): string {
  return PALETTE[i % PALETTE.length];
}

/** One track from a processed GPS stream (canonical point shape
 * `{t, lat, lon, speed_kn, course}` — worker output / GPX parse). */
export function buildTrack(id: string, name: string, points: GpsPoint[], color: string): Track {
  const pts: TrackPoint[] = points
    .filter((p) => p.lat != null && p.lon != null)
    .map((p) => ({
      ms: Date.parse(p.t),
      lat: p.lat,
      lon: p.lon,
      sog: p.speed_kn ?? 0,
    }))
    .sort((a, b) => a.ms - b.ms);
  return { id, name, color, pts };
}

/** Tracks from `GET /races/{id}/data` — sessions keyed by id, boat embedded. */
export function buildTracks(data: RaceData): Track[] {
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
