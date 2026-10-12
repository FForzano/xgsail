import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp } from "lucide-react";
import { sessionsService, sessionKeys } from "@/services/sessions";
import { polarsService, polarKeys } from "@/services/polars";
import { Section } from "@/components/ui/Section";
import { Spinner } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { StatTile, StatTiles } from "./StatTile";
import styles from "./SessionAnalysis.module.css";
import { fmtKnots } from "@/utils/format";
import { windSummary } from "@/utils/windStats";
import { WindChart } from "./WindChart";
import { PolarChart } from "./PolarChart";
import { LegsTable, TackBreakdown } from "./AnalysisLegs";
import { ManeuverSummary, ManeuversTable } from "./AnalysisManeuvers";
import type { PolarPoint, SessionAnalysis as SessionAnalysisData, SessionManeuver, UUID } from "@/types";

/** Rich per-session analysis (maneuvers, polar, VMG, …), assembled from its
 * normalized DB homes. 404 until the processing pipeline has run.
 *
 * Laid out synthesis-first: every block leads with its aggregates (tiles,
 * charts) and keeps the row-by-row list behind a collapsed toggle, because
 * most readers want the summary and only some want the raw legs/maneuvers.
 * The collapsed toggle always carries the row count, so "collapsed" never
 * reads as "empty".
 *
 * `editMode` (from the session page's options menu) surfaces per-maneuver
 * correct/reject/restore/delete actions on the table — see
 * `backend/routers/sessions.py::correct_maneuver/reject_maneuver/
 * delete_maneuver`. Outside edit mode, rejected maneuvers are hidden from
 * both the table and the summary/comparison charts below (they're not real
 * maneuvers, by the user's own say-so).
 *
 * `part` picks which tab of the session page this is: "performance" (legs,
 * maneuvers) or "wind" (the session's wind and its polar). */
export function SessionAnalysis({
  sessionId,
  part,
  editMode = false,
  maxSpeedKts,
  onRefreshWind,
  refreshingWind = false,
}: {
  sessionId: UUID;
  part: "performance" | "wind";
  editMode?: boolean;
  maxSpeedKts?: number | null;
  /** Reuses the boat manager's existing "refresh wind" action (see
   * SessionDetail) — offered from the "no wind data" message below.
   * Omitted for a caller who can't trigger it (not a manager). */
  onRefreshWind?: () => void;
  refreshingWind?: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [deletingManeuverId, setDeletingManeuverId] = useState<UUID | null>(null);
  const analysis = useQuery({
    queryKey: sessionKeys.analysis(sessionId),
    queryFn: () => sessionsService.analysis(sessionId),
    retry: false, // 404 = not computed yet
  });
  const polar = useQuery({
    queryKey: polarKeys.session(sessionId),
    queryFn: () => polarsService.forSession(sessionId),
  });

  const invalidateAnalysis = () => queryClient.invalidateQueries({ queryKey: sessionKeys.analysis(sessionId) });
  const correctManeuver = useMutation({
    mutationFn: ({ maneuverId, type }: { maneuverId: UUID; type: SessionManeuver["maneuver_type"] }) =>
      sessionsService.correctManeuver(sessionId, maneuverId, type),
    onSuccess: invalidateAnalysis,
  });
  const rejectManeuver = useMutation({
    mutationFn: ({ maneuverId, rejected }: { maneuverId: UUID; rejected: boolean }) =>
      sessionsService.rejectManeuver(sessionId, maneuverId, rejected),
    onSuccess: invalidateAnalysis,
  });
  const deleteManeuver = useMutation({
    mutationFn: (maneuverId: UUID) => sessionsService.deleteManeuver(sessionId, maneuverId),
    onSuccess: () => {
      setDeletingManeuverId(null);
      return invalidateAnalysis();
    },
  });

  if (analysis.isLoading) return <Section><Spinner /></Section>;
  if (!analysis.data) return null; // no analysis yet — hide the section entirely
  const a = analysis.data;
  const noWindData = a.unavailable_reason === "no_wind_data";
  const visibleManeuvers = editMode ? a.maneuvers : a.maneuvers.filter((m) => !m.rejected);
  const parts = analysisParts(a, editMode);
  if (part === "wind" && !parts.wind && !polar.data?.length) return null;
  if (part === "performance" && !noWindData && !parts.legs && !parts.maneuvers) return null;

  return (
    // No "Analysis" heading of its own: its first block's title would sit
    // right under it with nothing between, two ruled heads in a row.
    <Section>
      <div className="sf-section__body">
        {part === "performance" && noWindData && (
          <p className={styles.noWindData}>
            {t("sessions.analysisNoWindData")}
            {onRefreshWind && (
              <Button variant="ghost" onClick={onRefreshWind} disabled={refreshingWind}>
                {t("sessions.refreshWind")}
              </Button>
            )}
          </p>
        )}
        {part === "wind" && parts.wind && (
          <Section title={t("wind.title")}>
            <WindChart points={a.true_wind} />
          </Section>
        )}
        {part === "wind" && !!polar.data?.length && (
          <Section title={t("sessions.polar")}>
            <PolarChart points={polar.data} targetPoints={a.polar_target} />
            <OptimalAngles points={polar.data} targetPoints={a.polar_target} />
          </Section>
        )}
        {part === "performance" && parts.legs && (
          <Section title={t("sessions.legsSection")}>
            <TackBreakdown legs={a.legs} maxSpeedKts={maxSpeedKts} />
            <LegsTable legs={a.legs} />
          </Section>
        )}
        {part === "performance" && parts.maneuvers && (
          <Section title={t("sessions.maneuvers")}>
            <ManeuverSummary summary={a.maneuver_summary} violin={a.violin} maneuvers={visibleManeuvers} />
            {!!visibleManeuvers.length && (
              <CollapsibleList label={t("sessions.maneuversList")} count={visibleManeuvers.length}>
                <ManeuversTable
                  maneuvers={visibleManeuvers}
                  editMode={editMode}
                  onCorrect={(maneuverId, type) => correctManeuver.mutate({ maneuverId, type })}
                  onReject={(maneuverId, rejected) => rejectManeuver.mutate({ maneuverId, rejected })}
                  onDelete={setDeletingManeuverId}
                />
              </CollapsibleList>
            )}
          </Section>
        )}
      </div>
      {deletingManeuverId && (
        <ConfirmDialog
          title={t("common.delete")}
          message={t("sessions.deleteManeuverConfirm")}
          busy={deleteManeuver.isPending}
          onConfirm={() => deleteManeuver.mutate(deletingManeuverId)}
          onClose={() => setDeletingManeuverId(null)}
        />
      )}
    </Section>
  );
}

/** Which of the analysis blocks below have anything to show — shared with the
 * session page, which offers its Wind tab only when there is one to open. */
export function analysisParts(a: SessionAnalysisData, editMode = false) {
  const visibleManeuvers = editMode ? a.maneuvers : a.maneuvers.filter((m) => !m.rejected);
  return {
    wind: !!windSummary(a.true_wind),
    legs: !!a.legs.length,
    // No sensor and no station/model source means no wind-derived maneuvers
    // either, but a user-edited one (added by hand on the map) doesn't depend
    // on wind — this block still shows those exactly like the normal path.
    maneuvers: !!(a.maneuver_summary || a.violin || visibleManeuvers.length),
  };
}

/** A raw list kept out of the way until asked for. The count sits in the
 * toggle itself so a collapsed list is never mistaken for an empty one. */
function CollapsibleList({
  label,
  count,
  children,
}: {
  label: string;
  count: number;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <div className={styles.collapsible}>
      <button
        type="button"
        className={styles.collapsibleToggle}
        aria-expanded={open}
        aria-label={`${label} (${count})`}
        title={open ? t("common.collapse") : t("common.expand")}
        onClick={() => setOpen((v) => !v)}
      >
        <span className={styles.collapsibleLabel}>{label}</span>
        <span className={styles.countPill}>{count}</span>
        {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>
      {open && <div className={styles.collapsibleBody}>{children}</div>}
    </div>
  );
}

// --- optimal angles (best VMG angle from THIS session's own polar, not a reference polar) --

// No monohull sustains closer than this — below it, a bucket almost always
// means the session's wind direction (estimated from a model when there's no
// onboard sensor, see wind_lookup.py) is biased rather than genuine pointing.
const MIN_REALISTIC_UPWIND_TWA_DEG = 30;

function bestPolarAngle(
  points: PolarPoint[],
  targetPoints: PolarPoint[] | null | undefined,
  predicate: (twaDeg: number) => boolean,
): { angle: number; vmg: number; target: number } | null {
  const candidates = points.filter((p) => predicate(p.twa_deg) && p.vmg_kts != null);
  if (!candidates.length) return null;
  const best = candidates.reduce((a, b) => (b.vmg_kts! > a.vmg_kts! ? b : a));
  const sameAngle = (targetPoints ?? []).filter((p) => p.twa_deg === best.twa_deg);
  const target =
    sameAngle.find((p) => p.tws_kts === best.tws_kts) ??
    sameAngle.slice().sort((a, b) => Math.abs(a.tws_kts - best.tws_kts) - Math.abs(b.tws_kts - best.tws_kts))[0];
  return { angle: best.twa_deg, vmg: best.vmg_kts!, target: target?.speed_kts ?? best.speed_kts };
}

function OptimalAngles({
  points,
  targetPoints,
}: {
  points: PolarPoint[];
  targetPoints?: PolarPoint[] | null;
}) {
  const { t } = useTranslation();
  const upwind = bestPolarAngle(points, targetPoints,
    (twa) => twa >= MIN_REALISTIC_UPWIND_TWA_DEG && twa < 90);
  const downwind = bestPolarAngle(points, targetPoints, (twa) => twa >= 90);
  if (!upwind && !downwind) return null;

  return (
    <div className={styles.optimalAngles}>
      <p className={`sf-muted ${styles.optimalAnglesNote}`}>{t("sessions.optimalAnglesNote")}</p>
      {/* Two tiles only, and each carries a second line — the default 4-up grid
          would leave half a row empty and squeeze the sub-line. */}
      <StatTiles wide>
        {[
          ["upwind", upwind] as const,
          ["downwind", downwind] as const,
        ].map(
          ([type, res]) =>
            res && (
              <StatTile
                key={type}
                label={t(`sessions.${type}`)}
                value={
                  <>
                    {res.angle}°
                    <span className={styles.tileSub}>
                      {t("sessions.target")} {fmtKnots(res.target)} · VMG {fmtKnots(res.vmg)}
                    </span>
                  </>
                }
              />
            ),
        )}
      </StatTiles>
    </div>
  );
}
