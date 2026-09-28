import { useTranslation } from "react-i18next";
import { useWindAt } from "@/hooks/useWindAt";
import { Card } from "@/components/ui/Card";
import { fmtDateTime } from "@/utils/format";
import { topWindSources, windAgeMinutes, windSourceLabel } from "@/utils/windSnapshot";
import styles from "./WindCard.module.css";

/** Live wind value for a coordinate — the fused best estimate (same
 * estimator the per-session analysis uses; see
 * backend/services/wind_lookup.live_snapshot). Used by session/race pages
 * that have GPS but no wind data of their own. */
export function WindCard({ lat, lng, at }: { lat: number; lng: number; at?: string | null }) {
  const { t } = useTranslation();
  const { data: snapshot, isLoading } = useWindAt(lat, lng, at);

  if (isLoading) return null; // don't block the page on a best-effort card
  if (!snapshot) return null;

  const sources = topWindSources(snapshot);
  const observedAt = snapshot.latest_observed_at ?? snapshot.observed_at;

  return (
    <Card title={`${t("nav.wind", "Wind")} — ${windSourceLabel(snapshot, t)}`}>
      <div className="sf-tablewrap">
        <table className="sf-table">
          <tbody>
            <tr>
              <th>TWD</th>
              <td>{snapshot.twd_deg != null ? `${snapshot.twd_deg}°` : "—"}</td>
              <th>TWS</th>
              <td>{snapshot.tws_kts != null ? `${snapshot.tws_kts} kn` : "—"}</td>
              <th>Gust</th>
              <td>{snapshot.gust_kts != null ? `${snapshot.gust_kts} kn` : "—"}</td>
            </tr>
            <tr>
              <th colSpan={2}>{t("common.date")}</th>
              <td colSpan={4} className="sf-muted">
                {fmtDateTime(observedAt)}
                {snapshot.latest_observed_at != null && ` (${t("wind.ageMin", { minutes: windAgeMinutes(snapshot, Date.now()) })})`}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      {sources.length > 0 && (
        <div className={styles.sources}>
          <p className={`sf-muted ${styles.sourcesLabel}`}>{t("wind.sourcesLabel")}</p>
          <ul className={styles.sourcesList}>
            {sources.map((s, i) => (
              <li key={i} className="sf-muted">
                {t(`wind.sourceType.${s.type}`)}
                {s.name && ` — ${s.name}`}
                {` (${Math.round(s.weight_share * 100)}%)`}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
