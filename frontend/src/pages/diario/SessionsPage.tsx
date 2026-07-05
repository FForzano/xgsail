import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { sessionsService, sessionKeys } from "@/services/sessions";
import { boatsService, boatKeys } from "@/services/boats";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { fmtDateTime } from "@/utils/format";
import type { SessionStatus } from "@/types";

export function sessionStatusBadge(status: SessionStatus): string {
  return status === "processed"
    ? "sf-badge sf-badge--success"
    : status === "failed"
      ? "sf-badge sf-badge--danger"
      : "sf-badge sf-badge--warning";
}

export function SessionsPage() {
  const { t } = useTranslation();

  const sessions = useQuery({ queryKey: sessionKeys.mine, queryFn: sessionsService.listMine });
  const boats = useQuery({ queryKey: boatKeys.all, queryFn: () => boatsService.list() });

  if (sessions.isLoading) return <Spinner />;

  const boatName = (id: string) => boats.data?.find((b) => b.id === id)?.name ?? "—";

  return (
    <Card
      title={t("sessions.title")}
      actions={
        <Link to="/diario/sessioni/import">
          <Button>{t("sessions.import")}</Button>
        </Link>
      }
    >
      {sessions.data?.length === 0 ? (
        <EmptyState>{t("sessions.empty")}</EmptyState>
      ) : (
        <div className="sf-tablewrap">
          <table className="sf-table">
            <thead>
              <tr>
                <th>{t("sessions.start")}</th>
                <th>{t("sessions.boat")}</th>
                <th>{t("common.status")}</th>
              </tr>
            </thead>
            <tbody>
              {sessions.data?.map((s) => (
                <tr key={s.id}>
                  <td>
                    <Link to={`/diario/sessioni/${s.id}`}>{fmtDateTime(s.started_at)}</Link>
                  </td>
                  <td>{boatName(s.boat_id)}</td>
                  <td>
                    <span className={sessionStatusBadge(s.status)}>{s.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
