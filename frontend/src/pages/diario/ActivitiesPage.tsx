import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { activitiesService, activityKeys } from "@/services/activities";
import { Card } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { fmtDateTime } from "@/utils/format";

export function ActivitiesPage() {
  const { t } = useTranslation();
  const [type, setType] = useState("");
  const [mine, setMine] = useState(true);

  const activities = useQuery({
    queryKey: activityKeys.list({ type, mine: String(mine) }),
    queryFn: () => activitiesService.list({ type: type || undefined, mine }),
  });

  return (
    <Card title={t("activities.title")}>
      <div className="sf-form__row" style={{ alignItems: "end" }}>
        <Select
          label={t("activities.type")}
          id="act-type"
          value={type}
          onChange={(e) => setType(e.target.value)}
        >
          <option value="">{t("common.none")}</option>
          <option value="race">{t("activities.types.race")}</option>
          <option value="training">{t("activities.types.training")}</option>
          <option value="solo">{t("activities.types.solo")}</option>
        </Select>
        <label className="sf-check">
          <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />
          <span>{t("activities.mine")}</span>
        </label>
      </div>

      {activities.isLoading ? (
        <Spinner />
      ) : activities.data?.length === 0 ? (
        <EmptyState>{t("activities.empty")}</EmptyState>
      ) : (
        <div className="sf-tablewrap">
          <table className="sf-table">
            <thead>
              <tr>
                <th>{t("common.name")}</th>
                <th>{t("activities.type")}</th>
                <th>{t("gruppi.visibility")}</th>
                <th>{t("sessions.start")}</th>
              </tr>
            </thead>
            <tbody>
              {activities.data?.map((a) => (
                <tr key={a.id}>
                  <td>
                    <Link to={`/diario/activities/${a.id}`}>
                      {a.name ?? t(`activities.types.${a.type}`)}
                    </Link>
                  </td>
                  <td>
                    <span className="sf-badge">{t(`activities.types.${a.type}`)}</span>
                  </td>
                  <td>{t(`activities.visibility.${a.visibility}`)}</td>
                  <td className="sf-muted">{fmtDateTime(a.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
