import { useTranslation } from "react-i18next";
import { Wind } from "lucide-react";
import { CONTACT_EMAIL } from "@/config/links";
import styles from "./WindStationHintCard.module.css";

/** Manager-only nudge on club/group overview tabs: coverage from
 * NOAA/METAR/Cumulus is sparse, and local sailors often know a nearby
 * station the admins don't. No dismissal/backend cadence like
 * SupportPromptBanner — this is a static, always-shown hint. */
export function WindStationHintCard() {
  const { t } = useTranslation();
  const subject = encodeURIComponent(t("wind.stationHint.subject"));

  return (
    <div className={styles.card}>
      <Wind size={18} className={styles.icon} />
      <p className={styles.text}>
        {t("wind.stationHint.text")}{" "}
        <a href={`mailto:${CONTACT_EMAIL}?subject=${subject}`}>{t("wind.stationHint.cta")}</a>
      </p>
    </div>
  );
}
