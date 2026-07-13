import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { sessionsService, sessionKeys } from "@/services/sessions";
import { polarsService, polarKeys } from "@/services/polars";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { fmtDuration, fmtDistanceNm, fmtKnots, fmtSeconds } from "@/utils/format";
import { PolarChart } from "./PolarChart";
import { legSequence } from "@/utils/legSequence";
import type { PolarPoint, SessionLeg, SessionManeuver, UUID } from "@/types";

const MANEUVER_TYPES = ["tack", "gybe", "course_change"] as const;

/** Rich per-session analysis (maneuvers, polar, VMG, …), assembled from its
 * normalized DB homes. 404 until the processing pipeline has run.
 *
 * `editMode` (from the session page's options menu) surfaces per-maneuver
 * correct/reject/restore/delete actions on the table — see
 * `backend/routers/sessions.py::correct_maneuver/reject_maneuver/
 * delete_maneuver`. Outside edit mode, rejected maneuvers are hidden from
 * both the table and the summary/violin charts below (they're not real
 * maneuvers, by the user's own say-so). */
export function SessionAnalysis({ sessionId, editMode = false }: { sessionId: UUID; editMode?: boolean }) {
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

  if (analysis.isLoading) return <Card title={t("sessions.analysis")}><Spinner /></Card>;
  if (!analysis.data) return null; // no analysis yet — hide the section entirely
  const a = analysis.data;
  const visibleManeuvers = editMode ? a.maneuvers : a.maneuvers.filter((m) => !m.rejected);

  return (
    <Card title={t("sessions.analysis")}>
      <div className="sf-section__body">
        {a.maneuver_summary && <ManeuverSummary summary={a.maneuver_summary} />}
        {!!polar.data?.length && (
          <Section title={t("sessions.polar")}>
            <PolarChart points={polar.data} targetPoints={a.polar_target} />
            <OptimalAngles points={polar.data} targetPoints={a.polar_target} />
          </Section>
        )}
        {!!a.legs.length && (
          <Section title={t("sessions.legs")}>
            <LegsTable legs={a.legs} />
            <TackBreakdown legs={a.legs} />
          </Section>
        )}
        {!!visibleManeuvers.length && (
          <Section title={t("sessions.maneuvers")}>
            <ManeuversTable
              maneuvers={visibleManeuvers}
              editMode={editMode}
              onCorrect={(maneuverId, type) => correctManeuver.mutate({ maneuverId, type })}
              onReject={(maneuverId, rejected) => rejectManeuver.mutate({ maneuverId, rejected })}
              onDelete={setDeletingManeuverId}
            />
          </Section>
        )}
        {a.violin && (
          <Section title={t("sessions.maneuverCompare")}>
            <ViolinBars violin={a.violin} />
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
    </Card>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="sf-analysis__block">
      <h4 className="sf-analysis__title">{title}</h4>
      {children}
    </div>
  );
}

// --- maneuvers -------------------------------------------------------------------------

function ManeuverSummary({ summary }: { summary: Record<string, unknown> }) {
  const { t } = useTranslation();
  const rows = ["tacks", "gybes"] as const;
  const cols: [string, string][] = [
    ["count", t("sessions.count")],
    ["avg_speed_loss_kts", t("sessions.avgSpeedLoss")],
    ["avg_recovery_sec", t("sessions.avgRecovery")],
    ["avg_duration_sec", t("sessions.avgDuration")],
  ];
  return (
    <div className="sf-tablewrap">
      <table className="sf-table">
        <thead>
          <tr>
            <th />
            {cols.map(([, label]) => <th key={label}>{label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const g = (summary[r] ?? {}) as Record<string, number>;
            return (
              <tr key={r}>
                <th>{t(`sessions.${r}`)}</th>
                {cols.map(([key]) => (
                  <td key={key}>{g[key] != null ? g[key] : "—"}</td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ManeuversTable({
  maneuvers,
  editMode = false,
  onCorrect,
  onReject,
  onDelete,
}: {
  maneuvers: SessionManeuver[];
  editMode?: boolean;
  onCorrect?: (maneuverId: UUID, type: SessionManeuver["maneuver_type"]) => void;
  onReject?: (maneuverId: UUID, rejected: boolean) => void;
  onDelete?: (maneuverId: UUID) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="sf-tablewrap">
      <table className="sf-table">
        <thead>
          <tr>
            <th>{t("sessions.type")}</th>
            <th>{t("sessions.speedLoss")}</th>
            <th>{t("sessions.recovery")}</th>
            <th>{t("sessions.duration")}</th>
            <th>Δ°</th>
            {editMode && <th />}
          </tr>
        </thead>
        <tbody>
          {maneuvers.map((m) => (
            <tr key={m.id} className={m.rejected ? "sf-row--muted" : undefined}>
              <td>
                {editMode ? (
                  <span className="sf-maneuver-type-select">
                    <Select
                      label={t("sessions.correctManeuver")}
                      id={`maneuver-type-${m.id}`}
                      value={m.maneuver_type}
                      disabled={m.pending}
                      onChange={(e) => onCorrect?.(m.id, e.target.value as SessionManeuver["maneuver_type"])}
                    >
                      {MANEUVER_TYPES.map((type) => (
                        <option key={type} value={type}>
                          {t(`sessions.${type}`)}
                        </option>
                      ))}
                    </Select>
                  </span>
                ) : (
                  t(`sessions.${m.maneuver_type}`)
                )}
                {m.pending && <span className="sf-badge sf-badge--pending"> {t("sessions.computing")}</span>}
                {m.rejected && <span className="sf-badge"> {t("sessions.rejected")}</span>}
              </td>
              <td>{fmtKnots(m.speed_loss_kts)}</td>
              <td>{fmtSeconds(m.recovery_time_sec)}</td>
              <td>{fmtSeconds(m.duration_sec)}</td>
              <td>{Math.abs(m.heading_change_deg).toFixed(0)}°</td>
              {editMode && (
                <td>
                  {m.source === "manual" ? (
                    <Button variant="danger" className="sf-btn--sm" onClick={() => onDelete?.(m.id)}>
                      {t("common.delete")}
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      className="sf-btn--sm"
                      onClick={() => onReject?.(m.id, !m.rejected)}
                    >
                      {m.rejected ? t("sessions.restoreManeuver") : t("sessions.rejectManeuver")}
                    </Button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- legs ------------------------------------------------------------------------------

function LegsTable({ legs }: { legs: SessionLeg[] }) {
  const { t } = useTranslation();
  const seq = legSequence(legs);
  const ranked = legs.slice().sort((x, y) => y.avg_vmg_kts - x.avg_vmg_kts);
  return (
    <div className="sf-tablewrap">
      <table className="sf-table">
        <thead>
          <tr>
            <th>#</th>
            <th>{t("sessions.type")}</th>
            <th>VMG</th>
            <th>{t("sessions.avgSpeed")}</th>
            <th>{t("sessions.maxSpeed")}</th>
            <th>{t("sessions.distance")}</th>
            <th>{t("sessions.duration")}</th>
          </tr>
        </thead>
        <tbody>
          {ranked.map((l) => (
            <tr key={l.id}>
              <td>{seq.get(l.id)}</td>
              <td>{t(`sessions.${l.leg_type}`)}</td>
              <td>{fmtKnots(l.avg_vmg_kts)}</td>
              <td>{fmtKnots(l.avg_speed_kts)}</td>
              <td>{fmtKnots(l.max_speed_kts)}</td>
              <td>{fmtDistanceNm(l.distance_nm)}</td>
              <td>{fmtDuration(l.duration_sec)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- tack breakdown (per point-of-sail: best tack, longest leg, port vs starboard) -----

function tackAvg(legs: SessionLeg[], tack: "port" | "starboard",
                 key: "avg_vmg_kts" | "avg_speed_kts"): number | null {
  const vals = legs.filter((l) => l.tack === tack).map((l) => l[key]);
  return vals.length ? vals.reduce((sum, v) => sum + v, 0) / vals.length : null;
}

function TackBreakdown({ legs }: { legs: SessionLeg[] }) {
  const { t } = useTranslation();
  const seq = legSequence(legs);
  const byType = new Map<string, SessionLeg[]>();
  for (const l of legs) {
    if (l.leg_type === "reach") continue; // port/starboard comparison is only meaningful upwind/downwind
    byType.set(l.leg_type, [...(byType.get(l.leg_type) ?? []), l]);
  }
  if (!byType.size) return null;

  return (
    <>
      {[...byType.entries()].map(([legType, group]) => {
        const bestVmgLeg = group.reduce((a, b) => (b.avg_vmg_kts > a.avg_vmg_kts ? b : a));
        const bestSpeed = Math.max(...group.map((l) => l.max_speed_kts));
        const longest = group.reduce((a, b) => (b.distance_nm > a.distance_nm ? b : a));
        const avgDistance = group.reduce((sum, l) => sum + l.distance_nm, 0) / group.length;
        const avgDuration = group.reduce((sum, l) => sum + l.duration_sec, 0) / group.length;
        const stbdVmg = tackAvg(group, "starboard", "avg_vmg_kts");
        const portVmg = tackAvg(group, "port", "avg_vmg_kts");
        const stbdSpeed = tackAvg(group, "starboard", "avg_speed_kts");
        const portSpeed = tackAvg(group, "port", "avg_speed_kts");
        const bestTack: "starboard" | "port" =
          (stbdVmg ?? -Infinity) >= (portVmg ?? -Infinity) ? "starboard" : "port";

        return (
          <div key={legType} className="sf-tackblock">
            <h5 className="sf-tackblock__title">
              {t(`sessions.${legType}`)} <span className="sf-muted">({group.length})</span>
            </h5>
            <div className="sf-tablewrap">
              <table className="sf-table">
                <tbody>
                  <tr>
                    <th>{t("sessions.bestTack")}</th>
                    <td>{t(`sessions.tackSide.${bestTack}`)}</td>
                    <th>{t("sessions.bestLeg")}</th>
                    <td>#{seq.get(bestVmgLeg.id)}</td>
                  </tr>
                  <tr>
                    <th>{t("sessions.bestVmg")}</th>
                    <td>{fmtKnots(bestVmgLeg.avg_vmg_kts)}</td>
                    <th>{t("sessions.maxSpeed")}</th>
                    <td>{fmtKnots(bestSpeed)}</td>
                  </tr>
                  <tr>
                    <th>{t("sessions.longestLeg")}</th>
                    <td>#{seq.get(longest.id)} — {fmtDistanceNm(longest.distance_nm)}</td>
                    <th>{t("sessions.avgDuration")}</th>
                    <td>{fmtDuration(avgDuration)}</td>
                  </tr>
                  <tr>
                    <th>{t("sessions.avgDistance")}</th>
                    <td colSpan={3}>{fmtDistanceNm(avgDistance)}</td>
                  </tr>
                  <tr>
                    <th>{t("sessions.tackVmgStarboard")}</th>
                    <td>{stbdVmg != null ? fmtKnots(stbdVmg) : "—"}</td>
                    <th>{t("sessions.tackVmgPort")}</th>
                    <td>{portVmg != null ? fmtKnots(portVmg) : "—"}</td>
                  </tr>
                  <tr>
                    <th>{t("sessions.tackSpeedStarboard")}</th>
                    <td>{stbdSpeed != null ? fmtKnots(stbdSpeed) : "—"}</td>
                    <th>{t("sessions.tackSpeedPort")}</th>
                    <td>{portSpeed != null ? fmtKnots(portSpeed) : "—"}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </>
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
    <div className="sf-optimal-angles">
      <p className="sf-muted sf-optimal-angles__note">{t("sessions.optimalAnglesNote")}</p>
      <div className="sf-optimal-angles__row">
        {[
          ["upwind", upwind] as const,
          ["downwind", downwind] as const,
        ].map(
          ([type, res]) =>
            res && (
              <div key={type} className="sf-optimal-angles__tile">
                <span className="sf-optimal-angles__label">{t(`sessions.${type}`)}</span>
                <strong className="sf-optimal-angles__angle">{res.angle}°</strong>
                <span className="sf-muted">
                  {t("sessions.target")}: {fmtKnots(res.target)}
                </span>
                <span className="sf-muted">VMG: {fmtKnots(res.vmg)}</span>
              </div>
            ),
        )}
      </div>
    </div>
  );
}

// --- maneuver comparison (violin → grouped means) --------------------------------------

const VIOLIN_METRICS: [string, string][] = [
  ["speed_loss_kts", "kn"],
  ["recovery_time_sec", "s"],
  ["duration_sec", "s"],
];

function ViolinBars({ violin }: { violin: Record<string, Record<string, { mean: number }>> }) {
  const { t } = useTranslation();
  const data = VIOLIN_METRICS.map(([metric]) => ({
    metric,
    tack: violin.tack?.[metric]?.mean ?? 0,
    gybe: violin.gybe?.[metric]?.mean ?? 0,
  }));
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--sf-border)" strokeDasharray="2 3" />
        <XAxis dataKey="metric" tick={{ fontSize: 11 }} />
        <YAxis width={32} tick={{ fontSize: 11 }} />
        <Tooltip />
        <Legend />
        <Bar dataKey="tack" name={t("sessions.tacks")} fill="#2f9be0" />
        <Bar dataKey="gybe" name={t("sessions.gybes")} fill="#e0654f" />
      </BarChart>
    </ResponsiveContainer>
  );
}

