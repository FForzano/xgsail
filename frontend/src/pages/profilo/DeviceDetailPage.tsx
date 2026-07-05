import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { devicesService, deviceKeys } from "@/services/devices";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/api/client";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { InputField } from "@/components/ui/InputField";
import { fmtDateTime, fmtDuration } from "@/utils/format";
import { statusBadge } from "./DevicesPage";
import type { UUID } from "@/types";

export function DeviceDetailPage() {
  const { deviceId } = useParams<{ deviceId: UUID }>();
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [newKey, setNewKey] = useState<string | null>(null);
  const [rotating, setRotating] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [nickname, setNickname] = useState<string | null>(null);

  const device = useQuery({
    queryKey: deviceKeys.detail(deviceId!),
    queryFn: () => devicesService.get(deviceId!),
    enabled: !!deviceId,
  });
  const health = useQuery({
    queryKey: deviceKeys.health(deviceId!),
    queryFn: () => devicesService.health(deviceId!),
    enabled: !!deviceId && device.data?.status === "claimed",
    retry: false, // 404 = no snapshot yet, not an error
  });

  const rename = useMutation({
    mutationFn: (name: string) => devicesService.update(deviceId!, { nickname: name }),
    onSuccess: async () => {
      setNickname(null);
      await queryClient.invalidateQueries({ queryKey: deviceKeys.all });
    },
  });
  const rotate = useMutation({
    mutationFn: () => devicesService.rotateKey(deviceId!),
    onSuccess: (res) => {
      setRotating(false);
      setNewKey(res.device_api_key);
    },
    onError: (err) =>
      notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error"),
  });
  const revoke = useMutation({
    mutationFn: () => devicesService.revoke(deviceId!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: deviceKeys.all });
      navigate(-1);
    },
  });

  if (device.isLoading || !deviceId) return <Spinner />;
  if (!device.data) return null;
  const d = device.data;
  const h = health.data;

  return (
    <div className="sf-section__body">
      <Card
        title={
          <>
            {d.nickname ?? d.id.slice(0, 8)}{" "}
            <span className={statusBadge(d.status)}>{t(`devices.status.${d.status}`)}</span>
          </>
        }
        actions={
          d.status === "claimed" && (
            <span style={{ display: "flex", gap: "0.5rem" }}>
              <Button variant="ghost" className="sf-btn--sm" onClick={() => setRotating(true)}>
                {t("devices.rotateKey")}
              </Button>
              <Button variant="danger" className="sf-btn--sm" onClick={() => setRevoking(true)}>
                {t("devices.revoke")}
              </Button>
            </span>
          )
        }
      >
        <div className="sf-tablewrap">
          <table className="sf-table">
            <tbody>
              <tr>
                <th>{t("devices.nickname")}</th>
                <td>
                  {nickname === null ? (
                    <>
                      {d.nickname ?? "—"}{" "}
                      <Button
                        variant="ghost"
                        className="sf-btn--sm"
                        onClick={() => setNickname(d.nickname ?? "")}
                      >
                        {t("common.edit")}
                      </Button>
                    </>
                  ) : (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        rename.mutate(nickname);
                      }}
                      style={{ display: "flex", gap: "0.5rem", alignItems: "flex-end" }}
                    >
                      <InputField
                        label=""
                        id="nickname"
                        value={nickname}
                        onChange={(e) => setNickname(e.target.value)}
                      />
                      <Button type="submit" className="sf-btn--sm" disabled={rename.isPending}>
                        {t("common.save")}
                      </Button>
                    </form>
                  )}
                </td>
              </tr>
              <tr>
                <th>{t("devices.externalId")}</th>
                <td>{d.external_id ?? "—"}</td>
              </tr>
              <tr>
                <th>{t("devices.status.claimed")}</th>
                <td>{fmtDateTime(d.claimed_at)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>

      {d.status === "claimed" && (
        <Card title={t("devices.health")}>
          {health.isLoading ? (
            <Spinner />
          ) : !h ? (
            <p className="sf-muted">{t("devices.noHealth")}</p>
          ) : (
            <div className="sf-tablewrap">
              <table className="sf-table">
                <tbody>
                  {h.battery_pct != null && (
                    <tr>
                      <th>{t("devices.battery")}</th>
                      <td>
                        {h.battery_pct}%{h.battery_v != null ? ` (${h.battery_v} V)` : ""}
                      </td>
                    </tr>
                  )}
                  {h.firmware_version != null && (
                    <tr>
                      <th>{t("devices.firmware")}</th>
                      <td>{h.firmware_version}</td>
                    </tr>
                  )}
                  {h.uptime_s != null && (
                    <tr>
                      <th>{t("devices.uptime")}</th>
                      <td>{fmtDuration(h.uptime_s)}</td>
                    </tr>
                  )}
                  {typeof h.reported_at === "string" && (
                    <tr>
                      <th>{t("devices.lastReport")}</th>
                      <td>{fmtDateTime(h.reported_at)}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {rotating && (
        <ConfirmDialog
          title={t("devices.rotateKey")}
          message={t("devices.rotateKeyHint")}
          confirmLabel={t("devices.rotateKey")}
          busy={rotate.isPending}
          onConfirm={() => rotate.mutate()}
          onClose={() => setRotating(false)}
        />
      )}
      {revoking && (
        <ConfirmDialog
          title={t("devices.revoke")}
          message={t("devices.revokeConfirm")}
          confirmLabel={t("devices.revoke")}
          busy={revoke.isPending}
          onConfirm={() => revoke.mutate()}
          onClose={() => setRevoking(false)}
        />
      )}
      {newKey && (
        <Modal title={t("devices.newKey")} onClose={() => setNewKey(null)}>
          <p className="sf-muted">{t("devices.rotateKeyHint")}</p>
          <div className="sf-keybox">{newKey}</div>
          <div className="sf-form__actions">
            <Button
              variant="ghost"
              onClick={() => {
                void navigator.clipboard.writeText(newKey);
                notify(t("common.copied"), "success");
              }}
            >
              {t("common.copy")}
            </Button>
            <Button onClick={() => setNewKey(null)}>{t("common.close")}</Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
