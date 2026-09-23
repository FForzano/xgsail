import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/hooks/useAuth";
import { authService } from "@/services/auth";
import { BUY_ME_A_COFFEE_URL } from "@/config/links";
import { SlimBanner } from "@/components/common/SlimBanner";

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
    <SlimBanner
      tint="warning"
      icon="☕"
      text={t("support.reminder.text")}
      ctaLabel={t("support.cta")}
      ctaHref={BUY_ME_A_COFFEE_URL}
      ctaTarget="_blank"
      onCtaClick={() => void dismiss(true)}
      onDismiss={() => void dismiss(false)}
      dismissLabel={t("support.reminder.dismiss")}
    />
  );
}
