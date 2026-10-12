import { useTranslation } from "react-i18next";
import { fmtDistance, fmtDuration, fmtKnots } from "@/utils/format";
import { windSummary } from "@/utils/windStats";
import type { SessionStats, TrueWindPoint } from "@/types";
import { StatTile, StatTiles } from "./StatTile";

/** The outing at a glance, right under the map: how long, how far, how fast,
 * in how much wind. Wind takes the average-speed slot when the analysis has
 * it — it's the context every other number on the page is read against — and
 * average speed comes back when there's no wind to show, so the row is always
 * four tiles (the 4-up / 2×2 grid has no slot for a fifth). */
export function SessionSummary({
  stats,
  trueWind,
}: {
  stats: SessionStats;
  trueWind?: TrueWindPoint[] | null;
}) {
  const { t } = useTranslation();
  const wind = windSummary(trueWind);

  return (
    <StatTiles>
      <StatTile label={t("sessions.duration")} value={fmtDuration(stats.duration_s)} />
      <StatTile label={t("sessions.distance")} value={fmtDistance(stats.distance_m)} />
      <StatTile label={t("sessions.maxSpeed")} value={fmtKnots(stats.max_speed_kts)} />
      {wind ? (
        <StatTile label={t("sessions.avgWind")} value={fmtKnots(wind.meanKts)} />
      ) : (
        <StatTile label={t("sessions.avgSpeed")} value={fmtKnots(stats.avg_speed_kts)} />
      )}
    </StatTiles>
  );
}
