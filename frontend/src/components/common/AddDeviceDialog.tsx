import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Capacitor } from "@capacitor/core";
import { Info } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { ClaimDeviceDialog } from "@/components/common/ClaimDeviceDialog";
import { WatchClaimDialog } from "@/components/common/WatchClaimDialog";
import { E1InfoDialog } from "@/components/devices/E1InfoDialog";
import * as nativeWatch from "@/services/nativeWatch";
import type { UUID } from "@/types";
import styles from "./AddDeviceDialog.module.css";

type Owner = { owner_user_id?: UUID; owner_boat_id?: UUID; owner_club_id?: UUID };

function DeviceOptionCard({
  title,
  hint,
  disabled,
  badge,
  onClick,
  onInfoClick,
}: {
  title: string;
  hint: string;
  disabled?: boolean;
  /** Shown when `disabled` — defaults to `devices.add.soon`. Pass an
   * explicit label when the card is disabled for a different reason (e.g.
   * "app only" rather than "not built yet"), so the two aren't conflated. */
  badge?: string;
  onClick: () => void;
  /** Optional info affordance, shown as its own corner button so it stays
   * reachable even when the card itself is `disabled` (e.g. XGSail E1 on
   * web, where claiming needs the native app but the info page shouldn't). */
  onInfoClick?: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className={`sf-card ${styles.card}`}>
      <button type="button" className={styles.cardButton} disabled={disabled} onClick={onClick}>
        <span className={styles.cardTitle}>{title}</span>
        <span className={`sf-muted ${styles.cardHint}`}>{hint}</span>
        {disabled && <span className="sf-badge sf-badge--soon">{badge ?? t("devices.add.soon")}</span>}
      </button>
      {onInfoClick && (
        <button
          type="button"
          className={styles.infoButton}
          onClick={onInfoClick}
          aria-label={t("devices.e1.info.button")}
        >
          <Info size={14} strokeWidth={2} />
        </button>
      )}
    </div>
  );
}

/** Entry point for "add a device", opened in place of the old direct
 * ClaimDeviceDialog trigger (docs/device-protocol.md §8 for the XGSail E1
 * BLE flow this leads into). Only XGSail E1 is active today; Apple Watch,
 * Garmin and Polar are shown disabled ("in arrivo") — see
 * backend/routers/integrations.py, which reserves their API surface without
 * implementing it yet. XGSail E1 itself is disabled on web (BLE claiming
 * needs the native app) but tagged "solo app", not "in arrivo", since it's
 * available today — just not from this platform.
 *
 * Context-aware on `owner`: wearables are personal (a user connects their
 * own watch/account), so they're only offered from the personal devices
 * page (`owner_user_id`) — a boat or club claim only ever adds hardware. */
export function AddDeviceDialog({ owner, onClose }: { owner: Owner; onClose: () => void }) {
  const { t } = useTranslation();
  const [claimingXgsailE1, setClaimingXgsailE1] = useState(false);
  const [claimingWatch, setClaimingWatch] = useState(false);
  const [infoE1Open, setInfoE1Open] = useState(false);
  const isNative = Capacitor.isNativePlatform();
  // The Apple Watch companion is iOS-only (watchOS + WatchConnectivity).
  const isIOS = Capacitor.getPlatform() === "ios";
  const showWearables = owner.owner_user_id !== undefined;
  // Beyond "is this iOS": is there actually a paired watch with the
  // companion app installed? Without this, "Apple Watch" could be claimed
  // with no real device behind it (a stray phantom device record).
  const [watchPaired, setWatchPaired] = useState(false);
  useEffect(() => {
    if (!isIOS) return;
    void nativeWatch.isSupported().then(setWatchPaired);
  }, [isIOS]);

  if (claimingXgsailE1) {
    return <ClaimDeviceDialog owner={owner} onClose={onClose} />;
  }
  if (claimingWatch && owner.owner_user_id) {
    return <WatchClaimDialog userId={owner.owner_user_id} onClose={onClose} />;
  }

  return (
    <Modal title={t("devices.add.title")} onClose={onClose}>
      <div className={styles.grid}>
        <DeviceOptionCard
          title={t("devices.add.xgsailE1")}
          hint={isNative ? t("devices.add.xgsailE1Hint") : t("devices.add.nativeOnly")}
          disabled={!isNative}
          badge={t("devices.add.nativeOnlyBadge")}
          onClick={() => setClaimingXgsailE1(true)}
          onInfoClick={() => setInfoE1Open(true)}
        />
        {showWearables && (
          <>
            <DeviceOptionCard
              title={t("devices.add.appleWatch")}
              hint={
                !isIOS
                  ? t("devices.add.iosOnly")
                  : !watchPaired
                    ? t("devices.add.notPaired")
                    : t("devices.add.appleWatchHint")
              }
              disabled={!isIOS || !watchPaired}
              badge={isIOS ? t("devices.add.notPairedBadge") : t("devices.add.iosOnlyBadge")}
              onClick={() => setClaimingWatch(true)}
            />
            <DeviceOptionCard title={t("devices.add.garmin")} hint="" disabled onClick={() => {}} />
            <DeviceOptionCard title={t("devices.add.polar")} hint="" disabled onClick={() => {}} />
          </>
        )}
      </div>
      {!showWearables && <p className="sf-muted">{t("devices.add.personalOnly")}</p>}
      {infoE1Open && <E1InfoDialog onClose={() => setInfoE1Open(false)} />}
    </Modal>
  );
}
