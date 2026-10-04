import { ArrowUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import { fmtKnots, splitKnots } from "@/utils/format";
import styles from "./WindBadge.module.css";

/** Floating wind direction/speed pill for a map surface (see
 * useMapCenterWind for where the value comes from). Renders nothing without a
 * direction, which is also what a failed/absent lookup yields — no coverage
 * and no connectivity both simply mean "no badge". */
export function WindBadge({
  twdDeg,
  twsKts,
  gustKts,
  className = "",
}: {
  twdDeg: number | null | undefined;
  twsKts: number | null | undefined;
  gustKts?: number | null;
  className?: string;
}) {
  const { t } = useTranslation();
  if (twdDeg == null) return null;
  const mean = splitKnots(twsKts);
  const gust = gustKts != null ? splitKnots(gustKts) : null;
  const title =
    `${t("wind.mean")} ${fmtKnots(twsKts)}` + (gustKts != null ? ` · ${t("wind.gust")} ${fmtKnots(gustKts)}` : "");
  return (
    <div className={`${styles.wind} ${className}`} title={title}>
      <span
        className={styles.windArrow}
        // twd_deg is where the wind comes FROM; rotate by +180 so the arrow
        // shows the direction it's blowing TOWARD (flow), not the bearing to
        // its source.
        style={{ transform: `rotate(${(twdDeg + 180) % 360}deg)` }}
      >
        <ArrowUp size={16} strokeWidth={2.5} />
      </span>
      {/* "12–18 kn", the way forecasts and dock talk quote it: the mean,
          then how high the gusts reach — one reading, not two labels. */}
      <span className={styles.windSpeed}>
        {mean.value}
        {gust && <span className={styles.windGust}>–{gust.value}</span>} {mean.unit}
      </span>
    </div>
  );
}
