import type { SessionLeg, SessionManeuver } from "@/types";

const KN_TO_MS = 0.514444;
// A leg shorter than this is a transition between maneuvers, not a leg the
// sailor could have sailed better — it would top the ranking on noise alone.
const MIN_LEG_SEC = 60;

export type SessionLoss =
  | {
      kind: "maneuver";
      id: string;
      atSec: number;
      lostM: number;
      /** True when the pipeline didn't measure `distance_lost_m` and the
       * figure is derived from the speed dip instead. */
      estimated: boolean;
      maneuver: SessionManeuver;
    }
  | {
      kind: "leg";
      id: string;
      atSec: number;
      lostM: number;
      bestVmgKts: number;
      leg: SessionLeg;
    };

/** Metres a maneuver cost against sailing straight on at its entry speed.
 * The worker doesn't populate `distance_lost_m` yet, so the fallback treats
 * the dip as a triangle: down from `speed_before` to `speed_min` over the
 * turn, back up over the recovery. */
function maneuverLossM(m: SessionManeuver): { lostM: number; estimated: boolean } | null {
  if (m.distance_lost_m != null) return { lostM: m.distance_lost_m, estimated: false };
  const dipKts = m.speed_before_kts - m.speed_min_kts;
  const spanSec = m.duration_sec + m.recovery_time_sec;
  if (dipKts <= 0 || spanSec <= 0) return null;
  return { lostM: 0.5 * dipKts * KN_TO_MS * spanSec, estimated: true };
}

/** Where a session lost distance, worst first: each maneuver against no
 * slowdown, and each upwind/downwind leg against the best VMG this same
 * session reached on that point of sail. Comparing against the session's own
 * best — not a reference polar — keeps every figure something the sailor
 * demonstrably did on the day. */
export function sessionLosses(legs: SessionLeg[], maneuvers: SessionManeuver[]): SessionLoss[] {
  const losses: SessionLoss[] = [];

  for (const m of maneuvers) {
    if (m.rejected || m.pending) continue;
    const loss = maneuverLossM(m);
    if (!loss || loss.lostM < 1) continue;
    losses.push({ kind: "maneuver", id: m.id, atSec: m.start_time, maneuver: m, ...loss });
  }

  for (const type of ["upwind", "downwind"] as const) {
    const typed = legs.filter(
      (l) => l.leg_type === type && l.duration_sec >= MIN_LEG_SEC && l.avg_vmg_kts > 0,
    );
    if (typed.length < 2) continue;
    const best = Math.max(...typed.map((l) => l.avg_vmg_kts));
    for (const leg of typed) {
      const lostM = (best - leg.avg_vmg_kts) * KN_TO_MS * leg.duration_sec;
      if (lostM < 1) continue;
      losses.push({ kind: "leg", id: leg.id, atSec: leg.start_time, lostM, bestVmgKts: best, leg });
    }
  }

  return losses.sort((a, b) => b.lostM - a.lostM);
}
