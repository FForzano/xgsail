import { useState } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/hooks/useAuth";
import { authService } from "@/services/auth";
import { BUY_ME_A_COFFEE_URL } from "@/config/links";
import styles from "./SupportPromptBanner.module.css";

/** Dismissible reminder shown to authed users once the backend says it's due
 * (capabilities `support.shouldShow` — 30 days after registration, then
 * re-snoozed on every dismissal, see backend/support.py). Never blocks the
 * app: closing it or clicking the link both schedule the next reminder. */
export function SupportPromptBanner() {
  const { t } = useTranslation();
  const { caps, refreshCaps } = useAuth();
  const [hiding, setHiding] = useState(false);

  if (!caps?.support.shouldShow || hiding) return null;

  const dismiss = async (donated: boolean) => {
    setHiding(true);
    try {
      await authService.dismissSupportPrompt(donated);
    } finally {
      void refreshCaps();
    }
  };

  return (
    <div className={styles.banner} role="note">
      <span className={styles.text}>☕ {t("support.reminder.text")}</span>
      <a
        href={BUY_ME_A_COFFEE_URL}
        target="_blank"
        rel="noreferrer"
        className={styles.cta}
        onClick={() => void dismiss(true)}
      >
        {t("support.cta")}
      </a>
      <button
        type="button"
        className={styles.dismiss}
        onClick={() => void dismiss(false)}
        aria-label={t("support.reminder.dismiss")}
        title={t("support.reminder.dismiss")}
      >
        <X size={16} />
      </button>
    </div>
  );
}
