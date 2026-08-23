import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Area,
  ComposedChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { sessionKeys, sessionsService } from "@/services/sessions";
import { useStreamJson } from "@/hooks/useStreamJson";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/api/client";
import { timeController, useTimeState } from "@/stores/timeController";
import { Avatar } from "@/components/ui/Avatar";
import { Section } from "@/components/ui/Section";
import { StatTile, StatTiles } from "./StatTile";
import {
  energyRate,
  prepareSeries,
  sampleAt,
  seriesDomain,
  timeInZones,
  type PhysioSensor,
  type SeriesPoint,
} from "@/utils/physioSeries";
import { rampStep } from "@/utils/colorRamp";
import { fmtDuration, userLabel } from "@/utils/format";
import { fmtTime } from "@/utils/format";
import type { HrZones, ScalarSample, SessionPhysio, UUID } from "@/types";
import styles from "./HealthCard.module.css";

// Personal health data recorded by a crew member's watch during a session.
//
// Form: one short panel per metric, stacked, all sharing the session's time
// axis and playback cursor. Four metrics with four different units cannot share
// a y-scale, and a chart with a second y-axis on the right invites exactly the
// misreading it looks like it's avoiding — so each metric keeps its own scale
// and the panels stack instead. Single series per panel means the panel title
// carries the identity and no legend box is needed.

const PANEL_H = 76;

// Reused from the app's existing palette (raceModel's track colors and the
// --sf-warning token): validated for CVD-safe adjacent separation and ≥3:1
// contrast against the dark chart surface. Do not "fix" these by darkening —
// a darker amber collapses the red↔amber pair below the normal-vision floor.
const COLORS: Record<string, string> = {
  heart_rate: "#e0654f",
  energy_rate: "#e0b24a",
  hrv: "#9b6fe0",
  respiration: "#4fd0e0",
};

interface Panel {
  key: string;
  sensor: PhysioSensor;
  color: string;
  title: string;
  unit: string;
  series: SeriesPoint[];
  /** Dense and continuous (area) vs sparse and irregular (dots). */
  dense: boolean;
  decimals: number;
}

export function HealthCard({ sessionId }: { sessionId: UUID }) {
  const physio = useQuery({
    queryKey: sessionKeys.physio(sessionId),
    queryFn: () => sessionsService.physio(sessionId),
    enabled: !!sessionId,
  });

  // No card at all when there's nothing visible — not an empty one. The API
  // returns [] both for "nobody wore a watch" and "someone did, privately",
  // and the UI must not distinguish the two either.
  if (!physio.data?.length) return null;

  return (
    <div data-tour="activity-health">
      <Section title={<HealthTitle />}>
        {physio.data.map((entry) => (
          <MemberHealth key={entry.session_upload_id} sessionId={sessionId} entry={entry} />
        ))}
      </Section>
    </div>
  );
}

function HealthTitle() {
  const { t } = useTranslation();
  return <>{t("sessions.health.title")}</>;
}

function MemberHealth({ sessionId, entry }: { sessionId: UUID; entry: SessionPhysio }) {
  const { t } = useTranslation();
  const { tMin, tMax, cursor } = useTimeState();
  const queryClient = useQueryClient();
  const { notify } = useToast();

  // Each series is a separate blob; entry.streams is already scoped to this one
  // crew member, so no subject filter is needed here.
  const hrRaw = useStreamJson<ScalarSample>(entry.streams, "heart_rate");
  const energyRaw = useStreamJson<ScalarSample>(entry.streams, "energy");
  const hrvRaw = useStreamJson<ScalarSample>(entry.streams, "hrv");
  const respRaw = useStreamJson<ScalarSample>(entry.streams, "respiration");

  const hr = useMemo(() => prepareSeries(hrRaw, "heart_rate"), [hrRaw]);
  const energy = useMemo(() => prepareSeries(energyRaw, "energy"), [energyRaw]);
  const hrv = useMemo(() => prepareSeries(hrvRaw, "hrv"), [hrvRaw]);
  const resp = useMemo(() => prepareSeries(respRaw, "respiration"), [respRaw]);
  // Cumulative kcal plotted raw is a line that only goes up, which says nothing
  // about when the effort happened. The total lives in the tiles instead.
  const kcalPerMin = useMemo(() => energyRate(energy), [energy]);

  const panels: Panel[] = useMemo(
    () =>
      [
        {
          key: "heart_rate",
          sensor: "heart_rate" as PhysioSensor,
          color: COLORS.heart_rate,
          title: t("sessions.health.heartRate"),
          unit: t("sessions.health.bpm"),
          series: hr,
          dense: true,
          decimals: 0,
        },
        {
          key: "energy_rate",
          sensor: "energy" as PhysioSensor,
          color: COLORS.energy_rate,
          title: t("sessions.health.energyRate"),
          unit: t("sessions.health.kcalPerMin"),
          series: kcalPerMin,
          dense: true,
          decimals: 1,
        },
        {
          key: "hrv",
          sensor: "hrv" as PhysioSensor,
          color: COLORS.hrv,
          title: t("sessions.health.hrv"),
          unit: t("sessions.health.ms"),
          series: hrv,
          dense: false,
          decimals: 0,
        },
        {
          key: "respiration",
          sensor: "respiration" as PhysioSensor,
          color: COLORS.respiration,
          title: t("sessions.health.respiration"),
          unit: t("sessions.health.brpm"),
          series: resp,
          dense: false,
          decimals: 0,
        },
      ].filter((p) => p.series.length > 0),
    [t, hr, kcalPerMin, hrv, resp],
  );

  const setSharing = useMutation({
    mutationFn: (shared: boolean) => sessionsService.updatePhysioSharing(sessionId, shared),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: sessionKeys.physio(sessionId) });
    },
    onError: (err) =>
      notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error"),
  });

  const stats = entry.stats;

  return (
    <div className={styles.member}>
      <div className={styles.memberHead}>
        <Avatar
          profileImage={entry.user?.profile_image}
          firstName={entry.user?.first_name}
          lastName={entry.user?.last_name}
          size="sm"
        />
        <strong>{userLabel(entry.user)}</strong>
        {entry.shared && <span className="sf-badge">{t("sessions.health.sharedBadge")}</span>}
        {entry.is_self && (
          <label className={`sf-check ${styles.sharing}`} style={{ marginLeft: "auto" }}>
            <input
              type="checkbox"
              checked={entry.shared}
              disabled={setSharing.isPending}
              onChange={(e) => setSharing.mutate(e.target.checked)}
            />
            <span>{t("sessions.health.shareWithCrew")}</span>
          </label>
        )}
      </div>

      {stats && (
        <StatTiles>
          <StatTile
            label={t("sessions.health.avgHr")}
            value={fmtMetric(stats.avg_hr_bpm, t("sessions.health.bpm"), 0)}
          />
          <StatTile
            label={t("sessions.health.maxHr")}
            value={fmtMetric(stats.max_hr_bpm, t("sessions.health.bpm"), 0)}
          />
          <StatTile
            label={t("sessions.health.totalKcal")}
            value={fmtMetric(stats.total_kcal, t("sessions.health.kcal"), 0)}
          />
          <StatTile
            label={t("sessions.health.avgHrv")}
            value={fmtMetric(stats.avg_hrv_ms, t("sessions.health.ms"), 0)}
          />
        </StatTiles>
      )}

      {entry.hr_zones && hr.length > 0 && <ZoneBar zones={entry.hr_zones} hr={hr} />}

      {!entry.hr_zones && entry.is_self && hr.length > 0 && (
        <p className={`sf-muted ${styles.hint}`}>
          {t("sessions.health.completeProfileHint")}{" "}
          <Link to="/profilo/anagrafica">{t("sessions.health.completeProfileLink")}</Link>
        </p>
      )}

      <div className={styles.panels}>
        {panels.map((panel) => (
          <MetricPanel
            key={panel.key}
            panel={panel}
            tMin={tMin}
            tMax={tMax}
            cursor={cursor}
            zones={panel.key === "heart_rate" ? entry.hr_zones : null}
          />
        ))}
      </div>
    </div>
  );
}

function MetricPanel({
  panel,
  tMin,
  tMax,
  cursor,
  zones,
}: {
  panel: Panel;
  tMin: number;
  tMax: number;
  cursor: number;
  zones: HrZones | null;
}) {
  const atCursor = sampleAt(panel.series, cursor);
  const [lo, hi] = seriesDomain(panel.series);

  return (
    <div className={styles.panel}>
      <div className={styles.panelHead}>
        <span className={styles.panelTitle}>
          {panel.title} ({panel.unit})
        </span>
        <span className={styles.panelValue}>
          {atCursor == null ? "—" : `${atCursor.toFixed(panel.decimals)} ${panel.unit}`}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={PANEL_H}>
        <ComposedChart
          data={panel.series}
          margin={{ top: 2, right: 4, bottom: 0, left: 0 }}
          onMouseDown={(s) => {
            if (typeof s?.activeLabel === "number") timeController.seek(s.activeLabel);
          }}
        >
          {/* Shared with the map and the speed chart, so every panel's cursor
              lines up with the same instant of the outing. */}
          <XAxis dataKey="ms" type="number" domain={[tMin, tMax]} hide />
          <YAxis domain={[lo, hi]} hide />
          {/* Zone bands sit behind the trace: reading "which zone was I in" off
              a bare bpm number requires arithmetic the chart can just show. */}
          {zones?.zones.map((z, i) => (
            <ReferenceArea
              key={z.zone}
              y1={Math.max(z.min_bpm, lo)}
              y2={Math.min(z.max_bpm, hi)}
              fill={rampStep(i, zones.zones.length)}
              fillOpacity={0.18}
              stroke="none"
              ifOverflow="hidden"
            />
          ))}
          <Tooltip
            labelFormatter={(ms) => (typeof ms === "number" ? fmtTime(ms) : "")}
            formatter={(v) => [`${Number(v).toFixed(panel.decimals)} ${panel.unit}`, panel.title]}
          />
          {panel.dense ? (
            <Area
              type="monotone"
              dataKey="v"
              stroke={panel.color}
              strokeWidth={2}
              fill={panel.color}
              fillOpacity={0.15}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          ) : (
            // Sparse and irregular: HealthKit emits HRV and respiration at
            // unpredictable intervals, so drawing a connected line would
            // fabricate readings between the samples that exist.
            <Scatter dataKey="v" fill={panel.color} isAnimationActive={false} />
          )}
          <ReferenceLine x={cursor} stroke="#fff" strokeWidth={1} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function ZoneBar({ zones, hr }: { zones: HrZones; hr: SeriesPoint[] }) {
  const { t } = useTranslation();
  const seconds = useMemo(() => timeInZones(hr, zones.zones), [hr, zones]);
  const total = [...seconds.values()].reduce((a, b) => a + b, 0);
  if (total <= 0) return null;

  return (
    <div>
      <div className={styles.zoneBar} role="img" aria-label={t("sessions.health.timeInZones")}>
        {zones.zones.map((z, i) => {
          const s = seconds.get(z.zone) ?? 0;
          if (s <= 0) return null;
          return (
            <div
              key={z.zone}
              className={styles.zoneSegment}
              style={{ width: `${(s / total) * 100}%`, background: rampStep(i, zones.zones.length) }}
            />
          );
        })}
      </div>
      <div className={styles.zoneLegend}>
        {zones.zones.map((z, i) => {
          const s = seconds.get(z.zone) ?? 0;
          if (s <= 0) return null;
          return (
            <span key={z.zone} className={styles.zoneLegendItem}>
              <span
                className={styles.zoneDot}
                style={{ background: rampStep(i, zones.zones.length) }}
              />
              {t("sessions.health.zone", { n: z.zone })} {z.min_bpm}–{z.max_bpm}{" "}
              <span className={styles.zoneTime}>{fmtDuration(Math.round(s))}</span>
            </span>
          );
        })}
      </div>
      {/* An estimated maximum is not a measured one; say which this is. */}
      <p className={`sf-muted ${styles.zoneBasis}`}>
        {t(`sessions.health.basis.${zones.basis}`, { max: zones.hr_max_bpm })} ·{" "}
        {t(`sessions.health.method.${zones.method}`)}
      </p>
    </div>
  );
}

function fmtMetric(value: number | null, unit: string, decimals: number): string {
  if (value == null) return "—";
  return `${value.toFixed(decimals)} ${unit}`;
}
