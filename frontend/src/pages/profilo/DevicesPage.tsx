import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { devicesService, deviceKeys } from "@/services/devices";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { AddDeviceDialog } from "@/components/common/AddDeviceDialog";
import { fmtDateTime } from "@/utils/format";
import type { Device, DeviceType } from "@/types";

export function statusBadge(status: Device["status"]): string {
  return status === "claimed"
    ? "sf-badge sf-badge--success"
    : status === "revoked"
      ? "sf-badge sf-badge--danger"
      : "sf-badge sf-badge--warning";
}

export function DeviceTable({ devices, types }: { devices: Device[]; types?: DeviceType[] }) {
  const { t } = useTranslation();
  const typeName = (id: string) => types?.find((dt) => dt.id === id)?.name ?? "—";
  return (
    <div className="sf-tablewrap">
      <table className="sf-table">
        <thead>
          <tr>
            <th>{t("devices.nickname")}</th>
            <th>{t("devices.type")}</th>
            <th>{t("devices.externalId")}</th>
            <th>{t("common.status")}</th>
            <th>{t("devices.claimCode")}</th>
          </tr>
        </thead>
        <tbody>
          {devices.map((d) => (
            <tr key={d.id}>
              <td>
                <Link to={`/profilo/devices/${d.id}`}>{d.nickname ?? d.id.slice(0, 8)}</Link>
              </td>
              <td>{typeName(d.device_type_id)}</td>
              <td>{d.external_id ?? "—"}</td>
              <td>
                <span className={statusBadge(d.status)}>{t(`devices.status.${d.status}`)}</span>
              </td>
              <td className="sf-muted">
                {d.status === "unclaimed" && d.claim_code_expires_at
                  ? fmtDateTime(d.claim_code_expires_at)
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DevicesPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [claiming, setClaiming] = useState(false);

  const devices = useQuery({ queryKey: deviceKeys.all, queryFn: devicesService.list });
  const types = useQuery({ queryKey: deviceKeys.types, queryFn: devicesService.listTypes });

  if (devices.isLoading) return <Spinner />;

  // The Profilo page shows personal devices; boat/club devices live in their
  // own detail pages (docs/frontend-project.md).
  const personal = devices.data?.filter((d) => d.owner_user_id === user?.id) ?? [];

  return (
    <>
      <div className="sf-toolbar" style={{ justifyContent: "flex-end" }}>
        <Button onClick={() => setClaiming(true)}>{t("devices.claim")}</Button>
      </div>
      {personal.length === 0 ? (
        <EmptyState>{t("devices.empty")}</EmptyState>
      ) : (
        <DeviceTable devices={personal} types={types.data} />
      )}
      {claiming && (
        <AddDeviceDialog owner={{ owner_user_id: user!.id }} onClose={() => setClaiming(false)} />
      )}
    </>
  );
}
