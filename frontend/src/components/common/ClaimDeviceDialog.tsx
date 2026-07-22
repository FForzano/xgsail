import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Capacitor } from "@capacitor/core";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { devicesService, deviceKeys } from "@/services/devices";
import * as nativeBle from "@/services/nativeBle";
import type { ScannedDevice } from "@/services/nativeBle";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { InputField } from "@/components/ui/InputField";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/api/client";
import type { UUID } from "@/types";
import styles from "./deviceClaim.module.css";

// The XGSail E1's device-type row is still seeded as "SailFrames E1" (see
// backend/auth/seed.py) — matching on `parser_key` rather than `name` keeps
// this working regardless of whether/when that display name gets renamed,
// and (unlike `category`, which "Generic GPX" also shares) it uniquely
// identifies the E1 hardware adapter.
const XGSAIL_E1_PARSER_KEY = "sailframes_e1_csv";

type Phase = "idle" | "scanning" | "select" | "claiming" | "done";

/** XGSail E1 claim flow over BLE (docs/device-protocol.md §8.3) — reused for
 * personal, boat and club devices via `owner`. Native-app-only (opened from
 * AddDeviceDialog only when `Capacitor.isNativePlatform()`); the guard below
 * is defensive in case this is ever reached another way. */
export function ClaimDeviceDialog({
  owner,
  onClose,
}: {
  owner: { owner_user_id?: UUID; owner_boat_id?: UUID; owner_club_id?: UUID };
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [phase, setPhase] = useState<Phase>("idle");
  const [nickname, setNickname] = useState("");
  const [found, setFound] = useState<ScannedDevice[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [claimed, setClaimed] = useState<{ externalId: string } | null>(null);

  const claim = useMutation({
    mutationFn: async (scanned: ScannedDevice) => {
      const types = await devicesService.listTypes();
      const deviceType = types.find((dt) => dt.parser_key === XGSAIL_E1_PARSER_KEY);
      if (!deviceType) throw new Error("XGSail E1 device type not found");
      const ticket = await devicesService.createClaim({
        device_type_id: deviceType.id,
        nickname: nickname || undefined,
        ...owner,
      });
      return nativeBle.claimDevice(scanned, ticket.claim_code);
    },
    onSuccess: async (result) => {
      setClaimed({ externalId: result.externalId });
      setPhase("done");
      await queryClient.invalidateQueries({ queryKey: deviceKeys.all });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : err instanceof Error ? err.message : t("errors.generic"));
      setPhase("select");
    },
  });

  const scan = async () => {
    setError(null);
    setPhase("scanning");
    try {
      const devices = await nativeBle.scanForDevices();
      setFound(devices);
      setPhase("select");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.generic"));
      setPhase("idle");
    }
  };

  const close = async () => {
    await queryClient.invalidateQueries({ queryKey: deviceKeys.all });
    onClose();
  };

  if (!Capacitor.isNativePlatform()) {
    return (
      <Modal title={t("devices.claim")} onClose={onClose}>
        <p className="sf-muted">{t("devices.add.nativeOnly")}</p>
      </Modal>
    );
  }

  return (
    <Modal title={t("devices.claim")} onClose={close}>
      {phase === "done" && claimed ? (
        <>
          <p className="sf-badge sf-badge--success">{t("devices.claimed")}</p>
          <p>
            {nickname || ""} <span className="sf-muted">{claimed.externalId}</span>
          </p>
          <div className="sf-form__actions">
            <Button onClick={close}>{t("common.close")}</Button>
          </div>
        </>
      ) : phase === "scanning" || phase === "claiming" ? (
        <>
          <Spinner />
          <p className={styles.countdown}>
            {phase === "scanning" ? t("devices.ble.scanning") : t("devices.ble.claiming")}
          </p>
        </>
      ) : phase === "select" ? (
        <>
          {found.length === 0 ? (
            <p className="sf-muted">{t("devices.ble.noneFound")}</p>
          ) : (
            <div className="sf-strip">
              {found.map((d) => (
                <div key={d.bleId} className="sf-strip__item">
                  <span>{d.name ?? d.bleId}</span>
                  <Button
                    className="sf-btn--sm"
                    onClick={() => {
                      setPhase("claiming");
                      claim.mutate(d);
                    }}
                  >
                    {t("devices.ble.connect")}
                  </Button>
                </div>
              ))}
            </div>
          )}
          {error && <p className="sf-form__error">{error}</p>}
          <div className="sf-form__actions">
            <Button variant="ghost" onClick={() => void scan()}>
              {t("devices.ble.rescan")}
            </Button>
            <Button variant="ghost" onClick={close}>
              {t("common.close")}
            </Button>
          </div>
        </>
      ) : (
        <>
          <InputField
            label={t("devices.nickname")}
            id="claim-nickname"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
          />
          {error && <p className="sf-form__error">{error}</p>}
          <div className="sf-form__actions">
            <Button onClick={() => void scan()}>{t("devices.ble.scan")}</Button>
          </div>
        </>
      )}
    </Modal>
  );
}
