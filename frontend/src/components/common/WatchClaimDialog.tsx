import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Capacitor } from "@capacitor/core";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deviceKeys } from "@/services/devices";
import * as nativeWatch from "@/services/nativeWatch";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/api/client";
import type { UUID } from "@/types";

type Phase = "idle" | "claiming" | "done";

/** Pair an Apple Watch as a personal `wearable` device (docs/device-protocol.md
 * §9). Unlike the E1 there's no BLE scan — the phone claims the watch and holds
 * its device key (§8.3), so this is just a nickname + confirm. Native-app-only
 * (opened from AddDeviceDialog only on iOS). */
export function WatchClaimDialog({ userId, onClose }: { userId: UUID; onClose: () => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);

  const claim = useMutation({
    mutationFn: () => nativeWatch.claimWatch(userId),
    onSuccess: async () => {
      setPhase("done");
      await queryClient.invalidateQueries({ queryKey: deviceKeys.all });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : err instanceof Error ? err.message : t("errors.generic"));
      setPhase("idle");
    },
  });

  const close = async () => {
    await queryClient.invalidateQueries({ queryKey: deviceKeys.all });
    onClose();
  };

  if (Capacitor.getPlatform() !== "ios") {
    return (
      <Modal title={t("devices.watch.title")} onClose={onClose}>
        <p className="sf-muted">{t("devices.watch.iosOnly")}</p>
      </Modal>
    );
  }

  return (
    <Modal title={t("devices.watch.title")} onClose={close}>
      {phase === "done" ? (
        <>
          <p className="sf-badge sf-badge--success">{t("devices.claimed")}</p>
          <p className="sf-muted">{t("devices.watch.claimedHint")}</p>
          <div className="sf-form__actions">
            <Button onClick={close}>{t("common.close")}</Button>
          </div>
        </>
      ) : phase === "claiming" ? (
        <>
          <Spinner />
          <p>{t("devices.watch.claiming")}</p>
        </>
      ) : (
        <>
          <p className="sf-muted">{t("devices.watch.pairHint")}</p>
          {error && <p className="sf-form__error">{error}</p>}
          <div className="sf-form__actions">
            <Button
              onClick={() => {
                setPhase("claiming");
                claim.mutate();
              }}
            >
              {t("devices.watch.pair")}
            </Button>
          </div>
        </>
      )}
    </Modal>
  );
}
