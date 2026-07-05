import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { devicesService, deviceKeys } from "@/services/devices";
import { useCountdown, fmtCountdown } from "@/hooks/useCountdown";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { InputField } from "@/components/ui/InputField";
import { ApiError } from "@/api/client";
import type { ClaimTicket, UUID } from "@/types";

/** Claim flow (docs/device-protocol.md §2), reused for personal, boat and
 * club devices via `owner`: mint a code, show it with an expiry countdown,
 * poll until the device confirms. */
export function ClaimDeviceDialog({
  owner,
  onClose,
}: {
  owner: { owner_user_id?: UUID; owner_boat_id?: UUID; owner_club_id?: UUID };
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [typeId, setTypeId] = useState("");
  const [nickname, setNickname] = useState("");
  const [ticket, setTicket] = useState<ClaimTicket | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const types = useQuery({ queryKey: deviceKeys.types, queryFn: devicesService.listTypes });
  const remaining = useCountdown(ticket?.expires_at ?? null);

  // Poll the claimed status while the code is displayed.
  const claimed = useQuery({
    queryKey: ticket ? deviceKeys.detail(ticket.device_id) : ["devices", "none"],
    queryFn: () => devicesService.get(ticket!.device_id),
    enabled: ticket !== null,
    refetchInterval: (q) => (q.state.data?.status === "claimed" ? false : 5000),
  });
  const isClaimed = claimed.data?.status === "claimed";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setTicket(
        await devicesService.createClaim({
          device_type_id: typeId,
          nickname: nickname || undefined,
          ...owner,
        }),
      );
      await queryClient.invalidateQueries({ queryKey: deviceKeys.all });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("errors.generic"));
    } finally {
      setBusy(false);
    }
  };

  const close = async () => {
    await queryClient.invalidateQueries({ queryKey: deviceKeys.all });
    onClose();
  };

  return (
    <Modal title={t("devices.claim")} onClose={close}>
      {!ticket ? (
        <form onSubmit={submit}>
          <Select
            label={t("devices.type")}
            id="claim-type"
            value={typeId}
            onChange={(e) => setTypeId(e.target.value)}
            required
          >
            <option value="" disabled>
              …
            </option>
            {types.data?.map((dt) => (
              <option key={dt.id} value={dt.id}>
                {dt.name} ({dt.category})
              </option>
            ))}
          </Select>
          <InputField
            label={t("devices.nickname")}
            id="claim-nickname"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
          />
          {error && <p className="sf-form__error">{error}</p>}
          <div className="sf-form__actions">
            <Button type="submit" disabled={busy || !typeId}>
              {t("common.create")}
            </Button>
          </div>
        </form>
      ) : isClaimed ? (
        <>
          <p className="sf-badge sf-badge--success">{t("devices.claimed")}</p>
          <p>
            {claimed.data?.nickname ?? ""}{" "}
            <span className="sf-muted">{claimed.data?.external_id}</span>
          </p>
          <div className="sf-form__actions">
            <Button onClick={close}>{t("common.close")}</Button>
          </div>
        </>
      ) : (
        <>
          <div className="sf-claimcode">{ticket.claim_code}</div>
          {remaining > 0 ? (
            <p className="sf-countdown">{fmtCountdown(remaining)}</p>
          ) : (
            <p className="sf-form__error">{t("devices.claimExpired")}</p>
          )}
          <p className="sf-muted">{t("devices.claimHint")}</p>
          <p className="sf-muted">{t("devices.waiting")}</p>
          <div className="sf-form__actions">
            <Button
              variant="ghost"
              onClick={() => {
                void navigator.clipboard.writeText(ticket.claim_code);
              }}
            >
              {t("common.copy")}
            </Button>
            <Button variant="ghost" onClick={close}>
              {t("common.close")}
            </Button>
          </div>
        </>
      )}
    </Modal>
  );
}
