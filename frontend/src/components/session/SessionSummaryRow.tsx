import { useTranslation } from "react-i18next";
import { fmtDistance, fmtDuration, fmtKnots } from "@/utils/format";
import type { SessionStats } from "@/types";
import styles from "./SessionSummaryRow.module.css";

/** The session's totals as one ruled results line under the title — the row
 * a results sheet prints for each boat, not a grid of KPI tiles. */
export function SessionSummaryRow({ stats, maneuverCount }: { stats: SessionStats; maneuverCount?: number }) {
  const { t } = useTranslation();
  const cells: Array<[string, string]> = [
    [t("sessions.duration"), fmtDuration(stats.duration_s)],
    [t("sessions.distance"), fmtDistance(stats.distance_m)],
    [t("sessions.avgSpeed"), fmtKnots(stats.avg_speed_kts)],
    [t("sessions.maxSpeed"), fmtKnots(stats.max_speed_kts)],
  ];
  if (stats.avg_polar_pct != null) cells.push([t("sessions.losses.avgPolar"), `${Math.round(stats.avg_polar_pct)}%`]);
  if (maneuverCount != null) cells.push([t("sessions.maneuvers"), String(maneuverCount)]);

  return (
    <dl className={styles.row}>
      {cells.map(([label, value]) => (
        <div key={label} className={styles.cell}>
          <dt className={styles.label}>{label}</dt>
          <dd className={styles.value}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
