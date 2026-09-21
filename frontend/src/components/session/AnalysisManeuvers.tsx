import { useTranslation } from "react-i18next";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Pagination, usePagination } from "@/components/ui/Pagination";
import styles from "./SessionAnalysis.module.css";
import { fmtKnots, fmtSeconds } from "@/utils/format";
import type { SessionManeuver, UUID, ViolinMetric } from "@/types";

const MANEUVER_TYPES = ["tack", "gybe", "course_change"] as const;

/** Tacks and gybes reuse the map-pin tokens for the same two things, so a bar
 * and its markers on the track above are the same colour. Both are design
 * tokens rather than literals, so they follow the theme instead of pinning a
 * hex that only works against today's background. `summaryKey` is the plural
 * the analyzer's `maneuver_summary` uses for the same type. */
const MANEUVER_SERIES = [
  { key: "tack", summaryKey: "tacks", i18nKey: "sessions.tacks", color: "var(--sf-primary)" },
  { key: "gybe", summaryKey: "gybes", i18nKey: "sessions.gybes", color: "var(--sf-gybe)" },
  {
    key: "course_change",
    summaryKey: "course_changes",
    i18nKey: "sessions.course_changes",
    color: "var(--sf-success)",
  },
] as const;

type Violin = Record<string, Record<string, ViolinMetric>>;

/** Counts per maneuver type — and, because each chip carries its series colour,
 * the legend for the charts below.
 *
 * This replaced a `sf-table` of count + the three averages: the averages were
 * the very numbers the charts beside it already plot, so the table was a second
 * rendering of the same data that also forced a horizontal scroll on a phone.
 * Counts are the only thing it said that the charts don't. */
export function ManeuverCounts({
  summary,
  maneuvers,
}: {
  summary: Record<string, unknown> | null;
  maneuvers: SessionManeuver[];
}) {
  const { t } = useTranslation();

  return (
    <ul className={styles.countChips}>
      {MANEUVER_SERIES.map((s) => {
        const group = (summary?.[s.summaryKey] ?? null) as Record<string, number> | null;
        // The summary is computed once by the analyzer; fall back to the rows
        // actually on screen when a session predates it or it failed to store.
        const count =
          typeof group?.count === "number"
            ? group.count
            : maneuvers.filter((m) => m.maneuver_type === s.key).length;
        return (
          <li key={s.key} className={styles.countChip}>
            <span className={styles.swatch} style={{ background: s.color }} />
            {t(s.i18nKey)}
            <span className={styles.countPill}>{count}</span>
          </li>
        );
      })}
    </ul>
  );
}

// --- tacks vs gybes ---------------------------------------------------------------------

type MetricRow = { metric: string; [series: string]: string | number };
type Series = (typeof MANEUVER_SERIES)[number];

function metricRow(violin: Violin, series: readonly Series[], metric: string,
                   label: string, decimals: number): MetricRow {
  const row: MetricRow = { metric: label };
  for (const s of series) {
    const mean = violin[s.key]?.[metric]?.mean ?? 0;
    row[s.key] = mean;
    row[`${s.key}Label`] = mean.toFixed(decimals);
  }
  return row;
}

/** One chart per unit. The three metrics are knots and seconds, and a single
 * shared Y axis silently claimed they were comparable — a ~1 kn speed loss
 * rendered as a sliver next to a ~12 s recovery. Splitting by unit is the
 * only honest way to keep bar length meaning magnitude. */
function MetricChart({ unit, data, series }: { unit: string; data: MetricRow[]; series: readonly Series[] }) {
  return (
    <div className={styles.chart}>
      <span className={styles.chartUnit}>{unit}</span>
      <ResponsiveContainer width="100%" height={170}>
        <BarChart data={data} margin={{ top: 16, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--sf-border)" strokeDasharray="2 3" vertical={false} />
          <XAxis
            dataKey="metric"
            interval={0}
            tickLine={false}
            axisLine={{ stroke: "var(--sf-border)" }}
            tick={{ fontSize: 11, fill: "var(--sf-muted)" }}
          />
          <YAxis
            width={30}
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 10, fill: "var(--sf-muted)" }}
          />
          {series.map((s) => (
            <Bar key={s.key} dataKey={s.key} fill={s.color} radius={[3, 3, 0, 0]} maxBarSize={44}>
              {/* Values printed on the bars: a phone has no hover, so a tooltip
                  would be the only way to read an exact number and often isn't. */}
              <LabelList
                dataKey={`${s.key}Label`}
                position="top"
                fontSize={10}
                fill="var(--sf-muted)"
              />
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ManeuverStatsChart({ violin }: { violin: Violin }) {
  const { t } = useTranslation();
  // Tack and gybe always draw (an absent one is itself worth seeing as a gap);
  // course_change only exists when someone has corrected a maneuver into one,
  // and an always-empty third bar would just narrow the other two.
  const series = MANEUVER_SERIES.filter((s) => s.key !== "course_change" || !!violin.course_change);
  const speed = [metricRow(violin, series, "speed_loss_kts", t("sessions.speedLoss"), 2)];
  const times = [
    metricRow(violin, series, "recovery_time_sec", t("sessions.recovery"), 1),
    metricRow(violin, series, "duration_sec", t("sessions.duration"), 1),
  ];

  return (
    <div className={styles.chartGrid}>
      <MetricChart unit="kn" data={speed} series={series} />
      <MetricChart unit="s" data={times} series={series} />
    </div>
  );
}

// --- maneuver list ----------------------------------------------------------------------

/** `styles.rows` restyles the same markup as label/value rows below 700px —
 * see `LegsTable`. In edit mode the type cell (which holds a `Select`) and the
 * action cell each take a full row of their own. */
export function ManeuversTable({
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
  const { page, setPage, pageCount, pageItems } = usePagination(maneuvers);

  return (
    <>
      <div className={`sf-tablewrap ${styles.rows}`}>
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
            {pageItems.map((m) => (
              <tr key={m.id} className={m.rejected ? "sf-row--muted" : undefined}>
                <td data-head data-span>
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
                <td>
                  <span className={styles.cellLabel}>{t("sessions.speedLoss")}</span>{fmtKnots(m.speed_loss_kts)}</td>
                <td>
                  <span className={styles.cellLabel}>{t("sessions.recovery")}</span>{fmtSeconds(m.recovery_time_sec)}</td>
                <td>
                  <span className={styles.cellLabel}>{t("sessions.duration")}</span>{fmtSeconds(m.duration_sec)}</td>
                <td>
                  <span className={styles.cellLabel}>Δ°</span>{Math.abs(m.heading_change_deg).toFixed(0)}°</td>
                {editMode && (
                  <td data-span>
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
      <Pagination page={page} pageCount={pageCount} onPageChange={setPage} label={t("sessions.maneuversList")} />
    </>
  );
}
