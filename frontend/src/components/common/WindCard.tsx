import { useTranslation } from "react-i18next";
import { useWindAt } from "@/hooks/useWindAt";
import { Card } from "@/components/ui/Card";
import { fmtDateTime } from "@/utils/format";

/** Quick live wind value for a coordinate — a real station in range wins,
 * otherwise an unblended Open-Meteo candidate (see
 * backend/services/wind_lookup.live_snapshot). Used by session/race pages
 * that have GPS but no wind data of their own — not the rigorous
 * per-session estimate. */
export function WindCard({ lat, lng, at }: { lat: number; lng: number; at?: string | null }) {
  const { t } = useTranslation();
  const { data: snapshot, isLoading } = useWindAt(lat, lng, at);

  if (isLoading) return null; // don't block the page on a best-effort card
  if (!snapshot) return null;

  return (
    <Card title={`${t("nav.wind", "Wind")} — ${snapshot.station_name ?? snapshot.provider}`}>
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
                {fmtDateTime(snapshot.observed_at)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  );
}
