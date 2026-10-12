import type { SessionLeg, SessionManeuver } from "@/types";
import { MIN_LEG_SEC, maneuverLossM } from "./sessionLosses";

// The track's fastest fix only stands for the session's top speed when it
// agrees with the computed stat; otherwise it is a GPS spike the stat already
// filtered out, and the moment can't be placed honestly.
const TOP_SPEED_MATCH_KTS = 0.15;
// Below this share of the distance sailed, the metres lost stop being the
// story of the day: 1% of a 10 km outing is 100 m, roughly what a handful of
// ordinary tacks cost, so the good part leads instead.
export const SMALL_LOSS_SHARE = 0.01;

export type SessionHighlight =
  | { kind: "speed"; atMs: number; speedKts: number }
  | { kind: "leg"; atMs: number; leg: SessionLeg; of: number }
  | { kind: "maneuver"; atMs: number; maneuver: SessionManeuver; lostM: number; estimated: boolean; of: number };

/** The best of the outing, from the same data the losses are ranked on: the
 * top speed and when it happened, the best upwind and downwind leg by VMG,
 * and the tack or gybe that cost least. Each needs something to beat — two
 * legs or two turns of the same kind — so an item is left out rather than
 * crowned unopposed. */
export function sessionHighlights(
  legs: SessionLeg[],
  maneuvers: SessionManeuver[],
  maxSpeedKts: number | null | undefined,
  points: { ms: number; sog: number }[],
): SessionHighlight[] {
  const out: SessionHighlight[] = [];

  if (maxSpeedKts != null && maxSpeedKts > 0) {
    const fix = points.find((p) => Math.abs(p.sog - maxSpeedKts) <= TOP_SPEED_MATCH_KTS);
    if (fix) out.push({ kind: "speed", atMs: fix.ms, speedKts: maxSpeedKts });
  }

  for (const type of ["upwind", "downwind"] as const) {
    const typed = legs.filter((l) => l.leg_type === type && l.duration_sec >= MIN_LEG_SEC && l.avg_vmg_kts > 0);
    if (typed.length < 2) continue;
    const best = typed.reduce((a, b) => (b.avg_vmg_kts > a.avg_vmg_kts ? b : a));
    out.push({ kind: "leg", atMs: best.start_time * 1000, leg: best, of: typed.length });
  }

  let cleanest: Extract<SessionHighlight, { kind: "maneuver" }> | null = null;
  for (const type of ["tack", "gybe"] as const) {
    const scored = maneuvers.flatMap((m) => {
      if (m.maneuver_type !== type || m.rejected || m.pending) return [];
      const loss = maneuverLossM(m);
      return loss ? [{ maneuver: m, ...loss }] : [];
    });
    if (scored.length < 2) continue;
    const best = scored.reduce((a, b) => (b.lostM < a.lostM ? b : a));
    if (!cleanest || best.lostM < cleanest.lostM) {
      cleanest = { kind: "maneuver", atMs: best.maneuver.start_time * 1000, of: scored.length, ...best };
    }
  }
  if (cleanest) out.push(cleanest);

  return out;
}

/** Whether the day's losses are small enough that the highlights lead. With
 * no distance to measure against, only a session with no loss at all does. */
export function highlightsLead(totalLostM: number, distanceM: number | null | undefined): boolean {
  if (totalLostM <= 0) return true;
  return distanceM != null && distanceM > 0 && totalLostM <= distanceM * SMALL_LOSS_SHARE;
}
