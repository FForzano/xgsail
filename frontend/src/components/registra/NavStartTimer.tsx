import { useTranslation } from "react-i18next";
import { fmtCountdown, useSignedCountdown } from "@/hooks/useCountdown";
import { NavTile } from "./NavTile";
import styles from "./NavModeOverlay.module.css";

const PRESET_MINUTES = [5, 4, 3, 1];

// Under a minute to go, the countdown is the only thing anyone is looking at.
const URGENT_S = 60;

const atOffset = (seconds: number) => new Date(Date.now() + seconds * 1000).toISOString();

/** Race start timer. Unarmed it's a row of preset buttons; armed it becomes
 * the hero reading and keeps counting UP after the gun (useSignedCountdown),
 * because "1:23 since the start" is as useful as the countdown to it.
 *
 * `startsAt` is owned by the overlay so the rest of the display can tell
 * whether the timer has taken over the hero slot. */
export function NavStartTimer({
  startsAt,
  onChange,
}: {
  startsAt: string | null;
  onChange: (startsAt: string | null) => void;
}) {
  const { t } = useTranslation();
  const remaining = useSignedCountdown(startsAt);

  if (!startsAt) {
    return (
      <div className={styles.timerPresets}>
        <span className={styles.tileLabel}>{t("registra.nav.timer.title")}</span>
        <div className={styles.timerButtons}>
          {PRESET_MINUTES.map((minutes) => (
            <button
              key={minutes}
              type="button"
              className={styles.timerButton}
              onClick={() => onChange(atOffset(minutes * 60))}
            >
              {t("registra.nav.timer.set", { minutes })}
            </button>
          ))}
        </div>
      </div>
    );
  }

  // Sync to the gun: snap to the nearest whole minute, the universal fix for
  // "I started the timer two seconds late". Past the start it re-arms from the
  // next whole minute rather than snapping backwards to zero.
  const sync = () => onChange(atOffset(Math.max(60, Math.round(remaining / 60) * 60)));

  return (
    <div className={styles.timerArmed}>
      <NavTile
        label={t("registra.nav.timer.title")}
        value={fmtCountdown(remaining)}
        size="hero"
        tone={remaining >= 0 && remaining <= URGENT_S ? "warn" : "default"}
      />
      <div className={styles.timerButtons}>
        <button type="button" className={styles.timerButton} onClick={sync}>
          {t("registra.nav.timer.sync")}
        </button>
        <button type="button" className={styles.timerButton} onClick={() => onChange(null)}>
          {t("registra.nav.timer.reset")}
        </button>
      </div>
    </div>
  );
}
