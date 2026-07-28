// Sailing-instrument math for the navigation-mode display
// (components/registra/NavModeOverlay.tsx). Pure functions, no React, no
// units-store awareness — callers format the results.
//
// Angle convention throughout: TWA is SIGNED relative to the boat's course.
// Positive = the wind comes from starboard (starboard tack), negative = from
// port. |TWA| is 0 head-to-wind and 180 dead downwind, which is how a sailor
// reads it. The generic angle/great-circle helpers live in utils/geo.ts.

import { angleDelta } from "@/utils/geo";

const rad = (deg: number) => (deg * Math.PI) / 180;

/** Signed true wind angle: where the wind sits relative to the bow, given the
 * boat's course (COG) and the direction the wind blows FROM (TWD, the
 * meteorological convention `WindSnapshot.twd_deg` uses). */
export function trueWindAngle(cogDeg: number, twdDeg: number): number {
  return angleDelta(cogDeg, twdDeg);
}

export type Tack = "port" | "starboard";

export function tackOf(twaSigned: number): Tack {
  return twaSigned >= 0 ? "starboard" : "port";
}

/** Velocity made good toward the wind, in the same unit as `sogKts`. Positive =
 * gaining to windward (beating), negative = running away from it — the sign
 * carries real meaning here, so callers should show it as a direction, not as
 * a bare minus. */
export function vmg(sogKts: number, twaSigned: number): number {
  return sogKts * Math.cos(rad(twaSigned));
}
