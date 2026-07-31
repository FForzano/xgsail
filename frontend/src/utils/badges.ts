import type { SessionStatus } from "@/types";

export function sessionStatusBadge(status: SessionStatus): string {
  return status === "processed"
    ? "sf-badge sf-badge--success"
    : status === "failed"
      ? "sf-badge sf-badge--danger"
      : "sf-badge sf-badge--warning";
}

/** Regatta lifecycle (`REGATTA_STATUSES`): not started yet / racing now /
 * over. Only "active" is a positive state worth coloring — a finished regatta
 * is neutral history, not a success. */
export function regattaStatusBadge(status: string): string {
  return status === "active"
    ? "sf-badge sf-badge--success"
    : status === "scheduled"
      ? "sf-badge sf-badge--soon"
      : "sf-badge";
}

/** Race lifecycle (`RACE_STATUSES`) — same reading as the regatta one, plus
 * "abandoned", the only failure state here. */
export function raceStatusBadge(status: string): string {
  return status === "started"
    ? "sf-badge sf-badge--success"
    : status === "scheduled"
      ? "sf-badge sf-badge--soon"
      : status === "abandoned"
        ? "sf-badge sf-badge--danger"
        : "sf-badge";
}

/** Per-boat result status (`RESULT_STATUSES`): a proper finish, or one of the
 * scoring penalties (dnf/dns/dsq/ocs/ret), which all read the same way to a
 * competitor — the race scored against them. */
export function resultStatusBadge(status: string): string {
  return status === "finished" ? "sf-badge sf-badge--success" : "sf-badge sf-badge--danger";
}
