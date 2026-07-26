import type { MarkRole } from "@/types";

// Mirrors the DB check constraint (backend/db/models/activity.py MARK_ROLES)
// exactly — kept in sync manually since it's a small, rarely-changing enum.
export const MARK_ROLES: MarkRole[] = [
  "pin",
  "rc",
  "windward",
  "leeward",
  "gate_port",
  "gate_stbd",
  "offset",
  "drill",
  "finish_pin",
  "finish_rc",
];

// Short code shown inside a race-mark pin on the map (MapView) and next to
// its row in a marks list (ActivityDetailPage) — deliberately NOT each role's
// first letter, since several collide there (gate_port/gate_stbd both "g",
// finish_pin/finish_rc both "f"). Language-independent by design: the letters
// themselves aren't translated, a legend maps them to the translated role
// name instead (see activities.markRoles.* in the locale files).
export const MARK_ROLE_LETTERS: Record<MarkRole, string> = {
  pin: "P",
  rc: "R",
  windward: "W",
  leeward: "L",
  gate_port: "GP",
  gate_stbd: "GS",
  offset: "O",
  drill: "D",
  finish_pin: "FP",
  finish_rc: "FR",
};
