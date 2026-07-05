import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { devicesService, deviceKeys } from "@/services/devices";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ClaimDeviceDialog } from "@/components/common/ClaimDeviceDialog";
import { fmtDateTime, fmtDuration } from "@/utils/format";
import { statusBadge } from "@/pages/profilo/DevicesPage";
import type { Device, UUID } from "@/types";

/** One row of the club fleet-health table — health is a per-device blob, so
 * each row fans out its own (cached) query. Club fleets are small. */
function FleetRow({ device }: { device: Device }) {
  const { t } = useTranslation();
  const health = useQuery({
    queryKey: deviceKeys.health(device.id),
    queryFn: () => devicesService.health(device.id),
    enabled: device.status === "claimed",
    retry: false, // 404 = no snapshot yet
  });
  const h = health.data;
  return (
    <tr>
      <td>{device.nickname ?? device.external_id ?? device.id.slice(0, 8)}</td>
      <td>
        <span className={statusBadge(device.status)}>{t(`devices.status.${device.status}`)}</span>
      </td>
      <td>{h?.battery_pct != null ? `${h.battery_pct}%` : "—"}</td>
      <td>{h?.firmware_version ?? "—"}</td>
      <td>{h?.uptime_s != null ? fmtDuration(h.uptime_s) : "—"}</td>
      <td className="sf-muted">
        {typeof h?.reported_at === "string" ? fmtDateTime(h.reported_at) : t("devices.noHealth")}
      </td>
    </tr>
  );
}

/** Club device management: claim for the club + aggregated fleet health
 * (docs/frontend-project.md, "Pagine aggiuntive per chi gestisce un club"). */
export function ClubDevices({ clubId }: { clubId: UUID }) {
  const { t } = useTranslation();
  const [claiming, setClaiming] = useState(false);

  const devices = useQuery({ queryKey: deviceKeys.all, queryFn: devicesService.list });
  const clubDevices = devices.data?.filter((d) => d.owner_club_id === clubId) ?? [];

  return (
    <Card
      title={t("gruppi.fleetHealth")}
      actions={
        <Button className="sf-btn--sm" onClick={() => setClaiming(true)}>
          {t("devices.claim")}
        </Button>
      }
    >
      {clubDevices.length === 0 ? (
        <p className="sf-muted">{t("devices.empty")}</p>
      ) : (
        <div className="sf-tablewrap">
          <table className="sf-table">
            <thead>
              <tr>
                <th>{t("devices.nickname")}</th>
                <th>{t("common.status")}</th>
                <th>{t("devices.battery")}</th>
                <th>{t("devices.firmware")}</th>
                <th>{t("devices.uptime")}</th>
                <th>{t("devices.lastReport")}</th>
              </tr>
            </thead>
            <tbody>
              {clubDevices.map((d) => (
                <FleetRow key={d.id} device={d} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {claiming && (
        <ClaimDeviceDialog owner={{ owner_club_id: clubId }} onClose={() => setClaiming(false)} />
      )}
    </Card>
  );
}
