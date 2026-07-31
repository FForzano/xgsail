// Shared date/number formatters (timezone-safe: full timestamps go through
// Date, bare YYYY-MM-DD dates are noon-anchored so they don't shift a day).

import { unitsStore } from "@/stores/unitsStore";
import { normalizeDeg } from "@/utils/geo";

const KN_TO_KMH = 1.852;
const MS_TO_KN = 1.943844;

/** Metres per second (what the background-geolocation plugin reports) to
 * knots (what every other speed value in the app is expressed in). */
export function msToKnots(ms: number): number {
  return ms * MS_TO_KN;
}

export function fmtDate(date?: string | null): string {
  if (!date) return "—";
  const d = date.length === 10 ? new Date(date + "T12:00:00") : new Date(date);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** Span of a multi-day event (a regatta, an entry's validity). Collapses to a
 * single date when the event lasts one day or has no end, so callers don't
 * each re-derive "same day → don't repeat it". */
export function fmtDateRange(start?: string | null, end?: string | null): string {
  const from = fmtDate(start);
  if (!end || end === start) return from;
  return `${from} – ${fmtDate(end)}`;
}

export function fmtDateTime(ts?: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtTime(ms: number): string {
  return new Date(ms).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function fmtDuration(sec?: number | null): string {
  if (!sec) return "—";
  const m = Math.round(sec / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

/** Race/series points. Usually whole numbers, but redress and average-points
 * scoring produce halves — show the decimal only when there is one. */
export function fmtPoints(points?: number | null): string {
  if (points == null) return "—";
  return Number.isInteger(points) ? String(points) : points.toFixed(1);
}

export function fmtDistance(m?: number | null): string {
  if (m == null) return "—";
  if (unitsStore.get() === "metric") {
    const km = m / 1000;
    return `${km >= 10 ? km.toFixed(1) : km.toFixed(2)} km`;
  }
  const nm = m / 1852;
  return nm >= 10 ? `${nm.toFixed(1)} nm` : `${nm.toFixed(2)} nm`;
}

/** Same conversion as `fmtDistance` but from a nautical-miles input (e.g.
 * `SessionLeg.distance_nm`, already in nm rather than raw meters). */
export function fmtDistanceNm(nm?: number | null): string {
  return fmtDistance(nm == null ? null : nm * 1852);
}

/** Speed split into number and unit, for layouts that style the two
 * differently — a big instrument readout with a small unit beside it (see
 * components/registra/NavTile.tsx). `fmtKnots` is this, joined. */
export function splitKnots(k?: number | null): { value: string; unit: string } {
  if (unitsStore.get() === "metric") {
    return { value: k == null ? "—" : (k * KN_TO_KMH).toFixed(1), unit: "km/h" };
  }
  return { value: k == null ? "—" : k.toFixed(1), unit: "kn" };
}

export function fmtKnots(k?: number | null): string {
  if (k == null) return "—";
  const { value, unit } = splitKnots(k);
  return `${value} ${unit}`;
}

/** Nautical bearing notation: always three digits, so a heading readout keeps
 * a constant width instead of jumping as the boat swings through 9°/10°. */
export function fmtBearing(deg?: number | null): string {
  if (deg == null) return "—";
  return `${Math.round(normalizeDeg(deg)).toString().padStart(3, "0")}°`;
}

export function fmtSeconds(sec?: number | null): string {
  return sec == null ? "—" : `${sec.toFixed(1)} s`;
}

export function userLabel(u?: { first_name?: string | null; last_name?: string | null; email?: string } | null): string {
  if (!u) return "—";
  const name = [u.first_name, u.last_name].filter(Boolean).join(" ");
  return name || u.email || "—";
}
